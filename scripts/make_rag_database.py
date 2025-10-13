import pandas as pd 
import os.path as osp
import os

from lang_agent.rag.emb import QwenEmbeddings

from langchain.text_splitter import CharacterTextSplitter
from langchain_community.vectorstores import FAISS
from langchain_openai import OpenAIEmbeddings
from langchain.schema import Document

def main(save_path = "assets/xiaozhan_emb"):
    cat_f = "assets/xiaozhan_data/catering_end_category.csv"
    desc_f = "assets/xiaozhan_data/catering_end_dish.csv"

    df_cat = pd.read_csv(cat_f)
    df_desc = pd.read_csv(desc_f)

    id_desc_dic = {}
    for _, (id, name, desc) in df_cat[["id", "name", "description"]].iterrows():
        id_desc_dic[id] = f"{name}-{desc}"

    df_desc["cat_desc"] = df_desc["category_id"].map(id_desc_dic)
    
    data = []
    for _, (name, desc, px, cat_desc) in df_desc[["name", "description", "price", "cat_desc"]].iterrows():
        sen = f"茶名称：{name}|茶描述：{desc}|价格{px}|饮品类:{cat_desc}"
        data.append(sen)
    

    # texts = [Document(e) for e in data]
    texts = data
    embeddings = QwenEmbeddings(
        api_key=os.environ.get("ALI_API_KEY")
    )  
    # embeddings = OpenAIEmbeddings(
    #     model="text-embedding-v4",
    #     api_key=os.environ.get("ALI_API_KEY"),
    #     base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"
    # )
    # embeddings = OpenAIEmbeddings()

    if not osp.exists(save_path):
        # --- STEP 2: Create vector store ---
        # vectorstore = FAISS.from_documents(texts, embeddings)

        if os.environ.get("ALI_API_KEY") is None or os.environ.get("ALI_API_KEY") == "SOMESHIT":
            texts = [Document(e) for e in data]
            vectorstore = FAISS.from_documents(texts, embeddings)
        else:
            out_emb = embeddings.batch_embed_documents(texts)
            vectorstore = FAISS.from_embeddings(zip(texts, out_emb), embeddings)

        # --- STEP 3: SAVE the FAISS index to local files ---
        vectorstore.save_local(save_path)
        print(f"✅ Saved FAISS index to: {save_path}")

    # --- STEP 4: LOAD later from disk in a separate session ---
    # (You can imagine this being a new Python script.)
    loaded_vectorstore = FAISS.load_local(
        folder_path=save_path,
        embeddings=embeddings,
        allow_dangerous_deserialization=True  # Required for LangChain >= 0.1.1
    )
    print("✅ Loaded FAISS index successfully!")

    # --- STEP 5: Use the retriever/QA chain on the loaded store ---
    retriever = loaded_vectorstore.as_retriever(search_kwargs={
        "k":3
    })

    u = loaded_vectorstore.similarity_search("灯与尘", k=2)

    res = retriever.invoke("灯与尘")

    for doc in res:
        print(doc)
        print("==============================================")


if __name__ == "__main__":
    main()