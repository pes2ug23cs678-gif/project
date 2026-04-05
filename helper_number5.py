from helper_number2 import checked

def last_part(g_list):
    new_list = []
    end_list = ['cob', 'cbl', 'ccp', 'cpy', 'cobol']
    for i in range(0, len(g_list), 1):
        #This is the for loop to be seen over here, so, we may continue any further!!!
        inner_part = g_list[i].strip()
        new_part = inner_part.split('.')
        if checked(new_part[-1], end_list) == 1:
            #We would be doing the appending part over here!!!
            new_list.append(inner_part)
    #This is the ending of the for loop over here!!!
    return new_list
