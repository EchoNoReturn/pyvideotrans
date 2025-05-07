import base64
import hashlib
import os

def calculate_file_hash(file_path, algorithm_name='sha256'):
    chunk_size = 1024 * 1024  # 1MB
    offset = 0
    hash_value = ""  # 初始为空字符串

    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File does not exist: {file_path}")

    with open(file_path, 'rb') as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break

            # 转换为 Base64 字符串（与前端 FileSystem.readAsStringAsync(..., Base64) 一致）
            base64_chunk = base64.b64encode(chunk).decode('utf-8')

            # 计算当前块的 hash，Base64 编码后输入
            chunk_hash = hashlib.new(algorithm_name)
            chunk_hash.update(base64_chunk.encode('utf-8'))
            chunk_hash_b64 = base64.b64encode(chunk_hash.digest()).decode('utf-8')

            # 拼接前一个 hash 和当前块的 chunkHash（Base64字符串），再计算 hash
            combined = hash_value + chunk_hash_b64
            combined_hash = hashlib.new(algorithm_name)
            combined_hash.update(combined.encode('utf-8'))

            # 将当前 hash 的值作为 base64 字符串传给下一轮
            hash_value = base64.b64encode(combined_hash.digest()).decode('utf-8')

            offset += chunk_size

    # 最终 hash（转为十六进制，和前端 HEX 一致）
    final_hash = hashlib.new(algorithm_name)
    final_hash.update(hash_value.encode('utf-8'))
    return final_hash.hexdigest()


# if __name__ == "__main__":
#     file_path = "C:\\Users\\chen\\Desktop\\zh_14s.mp4"
#     hash_result = calculate_file_hash(file_path)
#     print(hash_result)