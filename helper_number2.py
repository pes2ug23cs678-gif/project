def checklen(lists, failure):
    if len(lists) == 0:
        #Failure is returned over here!!!
        print(f"Sorry, we cannot continue any further over here, for {failure}!!!")
        return 0
    return 1

def checked(string, lists):
    if string.lower() in lists:
        #Successful case over here!!!
        return 1
    return 0
