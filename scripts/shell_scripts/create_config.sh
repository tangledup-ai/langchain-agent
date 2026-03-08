SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$(dirname "$SCRIPT_DIR")")"

cd "$PROJECT_ROOT"

source ~/.bashrc
conda init
conda activate lang

echo create blueberry config
python scripts/py_scripts/misc_tasks.py --save-path configs/pipelines/blueberry.yaml \
										react \
										--sys-prompt-f configs/prompts/blueberry.txt \
			                 			--tool-manager-config.client-tool-manager.tool-keys

# echo create xiaozhan config
python scripts/py_scripts/misc_tasks.py --save-path configs/pipelines/xiaozhan.yaml