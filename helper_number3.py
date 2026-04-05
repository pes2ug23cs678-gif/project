#This is just to check if the given knowledge base is missing or not
import os
from helper_number1 import file_exists, check_number_2 #This is a better practice over here
def check_kb_status(source_file, kb_folder):
    #This is the next part over here
    file_name = os.path.basename(source_file)
    kb_path = os.path.join(kb_folder, file_name)
    if not file_exists(kb_path):
        return "MISSING"
    source_hash = check_number_2(source_file) #This is teh next part over here
    destination_hash = check_number_2(kb_path)
    if source_hash != destination_hash:
        return "OUTDATED" #This is teh next part over here
    return "EXISTS"
