import os
import json
import time
import argparse
import requests


def main() -> None:
	parser = argparse.ArgumentParser()
	parser.add_argument("--host", default=os.environ.get("VLLM_HOST", "http://127.0.0.1:8000"))
	parser.add_argument("--model", default=os.environ.get("VLLM_MODEL", "Qwen/Qwen2.5-7B-Instruct"))
	parser.add_argument("--prompt", default="介绍一下你的能力，简要回答。")
	args = parser.parse_args()

	url = f"{args.host}/v1/chat/completions"
	headers = {"Authorization": f"Bearer {os.environ.get('OPENAI_API_KEY', 'EMPTY')}", "Content-Type": "application/json"}
	payload = {
		"model": args.model,
		"messages": [{"role": "user", "content": args.prompt}],
		"temperature": 0.7,
	}
	resp = requests.post(url, headers=headers, data=json.dumps(payload), timeout=600)
	resp.raise_for_status()
	obj = resp.json()
	print(json.dumps(obj, ensure_ascii=False, indent=2))
	print("\nAnswer:\n", obj.get("choices", [{}])[0].get("message", {}).get("content", ""))


if __name__ == "__main__":
	main()


