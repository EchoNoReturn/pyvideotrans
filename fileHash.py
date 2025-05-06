import base64
import hashlib
import os
def digest_hex(algorithm_name, data_b64):
    data = base64.b64decode(data_b64)
    h = hashlib.new(algorithm_name)
    h.update(data)
    return h.hexdigest()
def calculate_file_hash(file_path, algorithm_name='sha256'):
    chunk_size = 1024 * 1024
    offset = 0
    hash_value = ""
    if not os.path.exists(file_path):
        raise FileNotFoundError("File does not exist")
    file_size = os.path.getsize(file_path)
    with open(file_path, 'rb') as f:
        while offset < file_size:
            f.seek(offset)
            f.read(chunk_size)
            hash_value = digest_hex(
                algorithm_name,
                base64.b64encode(hash_value.encode('utf-8')).decode('utf-8')
            )
            offset += chunk_size
    return digest_hex(
        algorithm_name,
        base64.b64encode(hash_value.encode('utf-8')).decode('utf-8')
    )
