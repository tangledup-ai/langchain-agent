source ~/.bashrc
conda init
conda activate lang

echo create blueberry config
python scripts/py_scripts/misc_tasks.py --save-path config/pipelines/blueberry.yaml \
										react \
										--sys-prompt-f configs/prompts/blueberry.txt \
			                 			--tool-manager-config.client-tool-manager.tool-keys

# echo create xiaozhan config
python scripts/py_scripts/misc_tasks.py --save-path config/pipelines/xiaozhan.yaml