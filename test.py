from transformers import AutoTokenizer

tokenizer = AutoTokenizer.from_pretrained(
    "Qwen/Qwen2.5-0.5B-Instruct",
    trust_remote_code=True
)

print(tokenizer)
print(tokenizer.chat_template is not None)