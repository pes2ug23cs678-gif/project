from helper_number1 import file_exists, save_to_knowledge_base
from helper_number2 import checklen
from helper_number3 import check_kb_status
from helper_number4 import chunk_by_procedure
from helper_number5 import last_part

def main():
    #This is the main function to be seen over here!!!!
    corpus = ['/home/genaiminiproject/project/data/Form1.cob', '/home/genaiminiproject/project/data/Global.asax.cob', '/home/genaiminiproject/project/data/Program1.cob']
    if checklen(corpus, "we are having an empty list over here") == 0:
        return
    #We can take the next step over here with ease!!!
    good_corpus = []
    for elements in corpus:
        if file_exists(elements) == 1:
            good_corpus.append(elements) #We could continue over here!!!
    if checklen(good_corpus, "we are not having any file that exists in the said locations") == 0:
        return
    g_list = []
    for e_file in good_corpus:
        destination = str() #THis is just in case over here!!!
        status = check_kb_status(e_file, destination)
        if status in ["MISSING", "OUTDATED"]:
            g_list.append(e_file) #THis is just towards the ending over here!!
    if checklen(g_list, "we are not having any element that is 'MISSING' or 'OUTDATED'") == 0:
        return
    new_list = last_part(g_list)
    if checklen(new_list, "we are not having any cobol files to work with") == 0:
        return
    for cobol_file in new_list:
        with open(cobol_file, 'r', encoding="utf-8") as f:
            raw_text = f.read()
            chunks = chunk_by_procedure(raw_text)
            for chunk in chunks:
                save_to_knowledge_base(chunk, metadata={"source": cobol_file})

if __name__ == "__main__":
    main() #This is how we would be starting with the program over here!!!
