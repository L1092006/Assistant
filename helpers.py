# Count the number of words/tokens. Currently words
# FIXME: implement tokens count
def count(str: str):
    return len(str.split(' '))

# Log to a file
def log(text, file_path: str = "log.txt", mode: str = "w"):
    with open(file_path, mode, encoding="utf-8") as f:
        f.write(f"{text}\n")