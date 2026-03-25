import os
import json
import argparse
import psycopg
from psycopg.rows import dict_row
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

def get_connection(conn_str=None):
    final_conn_str = conn_str or os.environ.get("CONN_STR")
    if not final_conn_str:
        raise ValueError("❌ 未找到数据库连接字符串。请在 .env 中配置 CONN_STR 或通过 --conn-str 参数提供。")
    return psycopg.connect(final_conn_str)

def init_db(conn_str=None):
    """初始化数据库表结构"""
    scripts = [
        "scripts/recreate_table.sql",      # 重置 messages 表
        "scripts/create_prompt_config.sql" # 创建配置表并预置数据
    ]
    
    print(f"🔌 正在连接数据库...")
    try:
        with get_connection(conn_str) as conn:
            with conn.cursor() as cur:
                for script_path in scripts:
                    if not os.path.exists(script_path):
                        print(f"⚠️ 跳过: 找不到文件 {script_path}")
                        continue
                        
                    print(f"📜 正在执行 {script_path}...")
                    with open(script_path, "r", encoding="utf-8") as f:
                        sql = f.read()
                        cur.execute(sql)
            conn.commit()
        print("✅ 数据库初始化完成！")
    except Exception as e:
        print(f"❌ 初始化失败: {e}")

def export_data(table_name, output_file, conn_str=None):
    """导出表数据到 JSON 文件"""
    print(f"🔌 正在连接数据库以导出 {table_name}...")
    try:
        with get_connection(conn_str) as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(f"SELECT * FROM {table_name}")
                rows = cur.fetchall()
                
                # 处理 datetime 对象，转为字符串
                for row in rows:
                    for k, v in row.items():
                        if hasattr(v, 'isoformat'):
                            row[k] = v.isoformat()
                            
                with open(output_file, "w", encoding="utf-8") as f:
                    json.dump(rows, f, ensure_ascii=False, indent=2)
        print(f"✅ 已将 {len(rows)} 条记录导出到 {output_file}")
    except Exception as e:
        print(f"❌ 导出失败: {e}")

def import_data(table_name, input_file, conn_str=None):
    """从 JSON 文件导入数据到表"""
    if not os.path.exists(input_file):
        print(f"❌ 找不到文件: {input_file}")
        return

    print(f"🔌 正在连接数据库以导入 {table_name}...")
    try:
        with open(input_file, "r", encoding="utf-8") as f:
            rows = json.load(f)
            
        if not rows:
            print("⚠️ JSON 文件为空，跳过导入。")
            return

        with get_connection(conn_str) as conn:
            with conn.cursor() as cur:
                # 获取列名
                columns = rows[0].keys()
                cols_str = ", ".join(columns)
                vals_str = ", ".join(["%s"] * len(columns))
                
                query = f"INSERT INTO {table_name} ({cols_str}) VALUES ({vals_str}) ON CONFLICT DO NOTHING"
                
                for row in rows:
                    values = [row[col] for col in columns]
                    cur.execute(query, values)
            conn.commit()
        print(f"✅ 已成功导入 {len(rows)} 条记录到 {table_name}")
    except Exception as e:
        print(f"❌ 导入失败: {e}")

def main():
    parser = argparse.ArgumentParser(description="数据库管理工具")
    parser.add_argument("--conn-str", help="数据库连接字符串 (默认使用 .env 中的 CONN_STR)")
    subparsers = parser.add_subparsers(dest="command", help="可用命令")

    # init 命令
    subparsers.add_parser("init", help="初始化数据库表结构 (运行 scripts/ 下的 SQL)")

    # export 命令
    export_parser = subparsers.add_parser("export", help="导出数据到 JSON")
    export_parser.add_argument("--table", required=True, help="要导出的表名 (如 messages, prompt_sets)")
    export_parser.add_argument("--out", required=True, help="输出文件路径 (如 data.json)")

    # import 命令
    import_parser = subparsers.add_parser("import", help="从 JSON 导入数据")
    import_parser.add_argument("--table", required=True, help="要导入的表名")
    import_parser.add_argument("--file", required=True, help="输入文件路径")

    args = parser.parse_args()

    if args.command == "init":
        init_db(args.conn_str)
    elif args.command == "export":
        export_data(args.table, args.out, args.conn_str)
    elif args.command == "import":
        import_data(args.table, args.file, args.conn_str)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
