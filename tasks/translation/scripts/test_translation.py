#!/usr/bin/env python3
"""
通用翻译测试脚本
支持通过命令行参数指定模型、输入文件、输出文件等
"""

import os
import sys
import time
import argparse
from openai import OpenAI

def translate_text(input_file, output_file, model="Qwen/Qwen3-32B-AWQ", 
                  temperature=0.1, max_tokens=16000, log_file=None):
    """通用翻译函数"""
    print(f"🧪 开始翻译测试...")
    print(f"📝 输入文件: {input_file}")
    print(f"📄 输出文件: {output_file}")
    print(f"🤖 模型: {model}")
    
    # 读取输入文件
    if not os.path.exists(input_file):
        print(f"❌ 输入文件不存在: {input_file}")
        return False
    
    with open(input_file, "r", encoding="utf-8") as f:
        input_text = f.read()
    
    print(f"📊 输入长度: {len(input_text)} 字符")
    
    # 构建prompt
    prompt = f"""请将以下日语文本翻译成中文，保持原文的段落结构和对话格式：

{input_text}

翻译结果："""
    
    try:
        client = OpenAI(base_url="http://localhost:8000/v1", api_key="dummy")
        
        print("🔬 开始翻译...")
        start_time = time.time()
        
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=temperature,
            max_tokens=max_tokens
        )
        
        end_time = time.time()
        translation = response.choices[0].message.content.strip()
        
        print(f"✅ 翻译完成！耗时: {end_time - start_time:.1f}秒")
        print(f"📊 翻译长度: {len(translation)} 字符")
        
        # 保存结果
        os.makedirs(os.path.dirname(output_file), exist_ok=True)
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(f"翻译时间: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"模型: {model}\n")
            f.write(f"输入文件: {input_file}\n")
            f.write(f"输入长度: {len(input_text)} 字符\n")
            f.write(f"翻译长度: {len(translation)} 字符\n")
            f.write(f"耗时: {end_time - start_time:.1f}秒\n")
            f.write("=" * 50 + "\n")
            f.write(translation)
        
        print(f"📄 结果已保存到: {output_file}")
        
        # 保存完整日志
        if log_file:
            os.makedirs(os.path.dirname(log_file), exist_ok=True)
            with open(log_file, "w", encoding="utf-8") as f:
                f.write(f"翻译时间: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"模型: {model}\n")
                f.write(f"输入文件: {input_file}\n")
                f.write(f"输出文件: {output_file}\n")
                f.write(f"输入长度: {len(input_text)} 字符\n")
                f.write(f"翻译长度: {len(translation)} 字符\n")
                f.write(f"耗时: {end_time - start_time:.1f}秒\n")
                f.write("=" * 50 + "\n")
                f.write("完整Prompt:\n")
                f.write(prompt)
                f.write("\n" + "=" * 50 + "\n")
                f.write("完整Response:\n")
                f.write(translation)
            
            print(f"📝 完整日志已保存到: {log_file}")
        
        # 显示前几行
        print("\n📊 翻译结果预览（前300字符）:")
        print("-" * 50)
        print(translation[:300] + "...")
        
        return True
        
    except Exception as e:
        print(f"❌ 翻译失败: {e}")
        return False

def main():
    parser = argparse.ArgumentParser(description="通用翻译测试脚本")
    parser.add_argument("--input", "-i", required=True, help="输入文件路径")
    parser.add_argument("--output", "-o", required=True, help="输出文件路径")
    parser.add_argument("--model", "-m", default="Qwen/Qwen3-32B-AWQ", help="使用的模型")
    parser.add_argument("--temperature", "-t", type=float, default=0.1, help="温度参数")
    parser.add_argument("--max-tokens", type=int, default=16000, help="最大token数")
    parser.add_argument("--log", help="日志文件路径（可选）")
    
    args = parser.parse_args()
    
    # 默认生成日志文件路径
    log_dir = "tasks/translation/logs"
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    log_file = args.log or f"{log_dir}/translation_{timestamp}.log"
    
    success = translate_text(
        input_file=args.input,
        output_file=args.output,
        model=args.model,
        temperature=args.temperature,
        max_tokens=args.max_tokens,
        log_file=log_file
    )
    
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()
