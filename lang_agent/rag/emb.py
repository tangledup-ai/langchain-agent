from langchain.embeddings.base import Embeddings
import dashscope
from dashscope import TextEmbedding
from typing import List
import asyncio
from concurrent.futures import ThreadPoolExecutor
from loguru import logger
import time

class QwenEmbeddings(Embeddings):
    """Custom Qwen embeddings using DashScope API"""
    
    def __init__(self, 
                 api_key: str, 
                 model: str = "text-embedding-v4",
                 max_workers: int = 5,
                 embedding_dimension: int = 512,
                 batch_size: int = 10,  # DashScope supports up to 10 texts per batch
                 rate_limit_delay: float = 0.00001):
        """
        Initialize Qwen embeddings
        
        Args:
            api_key: DashScope API key
            model: Model name (text-embedding-v1, text-embedding-v2, etc.)
            max_workers: Maximum number of concurrent workers for async operations
            embedding_dimension: Dimension of embedding vectors (adjust based on model)
            batch_size: Number of texts to process in one API call (max 10 for DashScope)
            rate_limit_delay: Delay between batches to respect rate limits
        """
        dashscope.api_key = api_key
        if api_key is None:
            logger.warning("no api_key provided!!")
            
        self.model = model
        self.max_workers = max_workers
        self.embedding_dimension = embedding_dimension
        self.batch_size = min(batch_size, 10)  # DashScope limit
        self.rate_limit_delay = rate_limit_delay
        
    def _get_batch_embeddings(self, texts: List[str]) -> List[List[float]]:
        """Get embeddings for a batch of texts using DashScope native batch API"""
        try:
            # DashScope supports batch processing natively
            response = TextEmbedding.call(
                model=self.model,
                input=texts  # Pass list directly
            )
            
            if response.status_code == 200:
                embeddings = []
                for embedding_data in response.output['embeddings']:
                    embeddings.append(embedding_data['embedding'])
                return embeddings
            else:
                logger.error(f"Batch API Error: {response.status_code}, {response.message}")
                # Return zero vectors as fallback
                return [[0.0] * self.embedding_dimension for _ in texts]
                
        except Exception as e:
            logger.error(f"Error embedding batch of {len(texts)} texts: {e}")
            # Return zero vectors as fallback
            return [[0.0] * self.embedding_dimension for _ in texts]
    
    def _get_single_embedding(self, text: str) -> List[float]:
        """Get embedding for a single text (fallback method)"""
        return self._get_batch_embeddings([text])[0]
    
    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """Embed a list of documents using smart batching"""
        if not texts:
            return []
            
        all_embeddings = []
        
        # Process in batches
        for i in range(0, len(texts), self.batch_size):
            batch = texts[i:i + self.batch_size]
            batch_num = i // self.batch_size + 1
            total_batches = (len(texts) + self.batch_size - 1) // self.batch_size
            
            logger.info(f"Processing batch {batch_num}/{total_batches} ({len(batch)} texts)")
            
            batch_embeddings = self._get_batch_embeddings(batch)
            all_embeddings.extend(batch_embeddings)
            
            # Add delay between batches to respect rate limits (except for last batch)
            if i + self.batch_size < len(texts) and self.rate_limit_delay > 0:
                time.sleep(self.rate_limit_delay)
        
        return all_embeddings
    
    def embed_query(self, text: str) -> List[float]:
        """Embed a single query text"""
        return self._get_single_embedding(text)
    
    async def aembed_documents(self, texts: List[str]) -> List[List[float]]:
        """Embed a list of documents asynchronously with smart batching"""
        if not texts:
            return []
            
        loop = asyncio.get_event_loop()
        
        # Create batches
        batches = [texts[i:i + self.batch_size] for i in range(0, len(texts), self.batch_size)]
        
        async def process_batch_with_delay(batch: List[str], batch_idx: int) -> List[List[float]]:
            """Process a single batch with rate limiting"""
            # Add delay before processing (except first batch)
            if batch_idx > 0 and self.rate_limit_delay > 0:
                await asyncio.sleep(self.rate_limit_delay)
            
            # Run the batch embedding in executor
            return await loop.run_in_executor(
                None, 
                self._get_batch_embeddings, 
                batch
            )
        
        # Process batches with controlled concurrency
        semaphore = asyncio.Semaphore(self.max_workers)
        
        async def process_batch_limited(batch: List[str], batch_idx: int) -> List[List[float]]:
            async with semaphore:
                logger.info(f"Processing async batch {batch_idx + 1}/{len(batches)} ({len(batch)} texts)")
                return await process_batch_with_delay(batch, batch_idx)
        
        # Execute all batches
        tasks = [
            process_batch_limited(batch, idx) 
            for idx, batch in enumerate(batches)
        ]
        
        batch_results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Flatten results and handle exceptions
        all_embeddings = []
        for i, batch_result in enumerate(batch_results):
            if isinstance(batch_result, Exception):
                logger.error(f"Error processing async batch {i}: {batch_result}")
                # Add zero vectors for failed batch
                batch_size = len(batches[i])
                all_embeddings.extend([[0.0] * self.embedding_dimension] * batch_size)
            else:
                all_embeddings.extend(batch_result)
        
        return all_embeddings
    
    async def aembed_query(self, text: str) -> List[float]:
        """Embed a single query text asynchronously"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._get_single_embedding, text)
    
    def get_embedding_dimension(self) -> int:
        """Get the dimension of embeddings"""
        return self.embedding_dimension
    
    def batch_embed_documents(self, texts: List[str], batch_size: int = None) -> List[List[float]]:
        """
        Embed documents in batches (legacy method - now just calls embed_documents)
        
        Args:
            texts: List of texts to embed
            batch_size: Batch size (if None, uses instance default)
        """
        if batch_size is not None and batch_size != self.batch_size:
            # Temporarily override batch size
            original_batch_size = self.batch_size
            self.batch_size = min(batch_size, 10)
            try:
                return self.embed_documents(texts)
            finally:
                self.batch_size = original_batch_size
        else:
            return self.embed_documents(texts)
    
    async def abatch_embed_documents(self, texts: List[str], batch_size: int = None) -> List[List[float]]:
        """
        Embed documents in batches asynchronously (legacy method - now just calls aembed_documents)
        
        Args:
            texts: List of texts to embed
            batch_size: Batch size (if None, uses instance default)
        """
        if batch_size is not None and batch_size != self.batch_size:
            # Temporarily override batch size
            original_batch_size = self.batch_size
            self.batch_size = min(batch_size, 10)
            try:
                return await self.aembed_documents(texts)
            finally:
                self.batch_size = original_batch_size
        else:
            return await self.aembed_documents(texts)
    
    def estimate_cost(self, texts: List[str], cost_per_1k_tokens: float = 0.0007) -> dict:
        """
        Estimate the cost of embedding the given texts
        
        Args:
            texts: List of texts to estimate cost for
            cost_per_1k_tokens: Cost per 1000 tokens (adjust based on current pricing)
            
        Returns:
            Dict with cost estimation details
        """
        # Rough estimation: ~1 token per 4 characters for Chinese/English mixed text
        total_chars = sum(len(text) for text in texts)
        estimated_tokens = total_chars / 4
        estimated_cost = (estimated_tokens / 1000) * cost_per_1k_tokens
        batches_needed = (len(texts) + self.batch_size - 1) // self.batch_size
        
        return {
            "total_texts": len(texts),
            "total_characters": total_chars,
            "estimated_tokens": int(estimated_tokens),
            "estimated_cost_usd": round(estimated_cost, 4),
            "batches_needed": batches_needed,
            "estimated_time_seconds": batches_needed * self.rate_limit_delay
        }

if __name__ == "__main__":
    # EXAMPLE USAGE
    embeddings = QwenEmbeddings(api_key="YOUR KEY")

    vector = embeddings.embed_query("Qwen embeddings are powerful for bilingual tasks.")

    print(vector)