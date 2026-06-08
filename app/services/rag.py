import logging
import os
import time
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough
from langchain_text_splitters import RecursiveCharacterTextSplitter

logger = logging.getLogger(__name__)


def get_llm() -> ChatOpenAI:
    return ChatOpenAI(
        model="gpt-4o-mini",
        openai_api_key=os.getenv("OPENAI_API_KEY"),
        temperature=0.2,
    )


def chunk_text(text: str) -> list[str]:
    splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
    chunks = splitter.split_text(text)
    logger.debug(f"[CHUNK] Split into {len(chunks)} chunks (size=1000, overlap=200)")
    return chunks


def answer_question(vectorstore, question: str) -> str:
    t0 = time.time()
    k           = int(os.getenv("RETRIEVAL_K", "3"))
    fetch_k     = int(os.getenv("RETRIEVAL_FETCH_K", "10"))
    lambda_mult = float(os.getenv("RETRIEVAL_LAMBDA", "0.7"))

    logger.info(f"[RETRIEVE] Question: '{question[:120]}{'...' if len(question) > 120 else ''}'")
    logger.info(f"[RETRIEVE] MMR — k={k}, fetch_k={fetch_k}, lambda={lambda_mult}")

    retriever = vectorstore.as_retriever(
        search_type="mmr",
        search_kwargs={"k": k, "fetch_k": fetch_k, "lambda_mult": lambda_mult},
    )

    prompt = ChatPromptTemplate.from_template(
        "Answer the question based only on the context below.\n\n"
        "Context:\n{context}\n\n"
        "Question: {question}"
    )

    logger.info("[LLM] Calling gpt-4o-mini...")
    chain = (
        {"context": retriever, "question": RunnablePassthrough()}
        | prompt
        | get_llm()
        | StrOutputParser()
    )

    answer = chain.invoke(question)
    logger.info(f"[LLM] Done — answer_length={len(answer)} chars, total_time={time.time()-t0:.2f}s")
    return answer
