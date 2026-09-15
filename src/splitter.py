from langchain_text_splitters import RecursiveCharacterTextSplitter


def split_docs(documents):
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000,
        chunk_overlap=200,
    )
    return splitter.split_documents(documents)


def split_documents(documents):
    return split_docs(documents)
