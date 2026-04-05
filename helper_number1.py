import os
import hashlib

#We are keeping this code so that we can include modularity over here!!!
def file_exists(element):
    if os.path.exists(element):
        return 1 #We could continue over here!!!
    return 0 #This is the failure phase to be seen over here!!!

def check_number_2(element):
    hasher = hashlib.md5() #This is the first step to be seen over here!!!
    with open(element, "rb", encoding="utf-8") as f:
        buf = f.read() #We are doing the reading part over here
        hasher.update(buf)
    return hasher.hexdigest()

def save_to_knowledge_base(chunk, metadata, output_folder="./kb_cleaned"):
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)
    # Create a unique filename for each chunk
    source_name = os.path.basename(metadata['source']).split('.')[0]
    chunk_id = hashlib.md5(chunk.encode()).hexdigest()[:8]
    file_path = os.path.join(output_folder, f"{source_name}_{chunk_id}.txt")
    with open(file_path, "w", encoding="utf_8") as f:
        f.write(chunk)
