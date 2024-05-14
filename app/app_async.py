import streamlit as st
import pandas as pd
import time
import os
from dotenv import load_dotenv
from openai import AzureOpenAI, AsyncAzureOpenAI
import numpy as np
from tenacity import (
    retry,
    stop_after_attempt,
    wait_random_exponential,
)  # for exponential backoff
import asyncio
import random

gpt_relevance_prompt_sys = """You are an AI assistant. You will be given the definition of an evaluation metric for assessing the quality of an answer in a question-answering task. Your job is to compute an accurate evaluation score using the provided evaluation metric."""
gpt_relevance_prompt_user = """
Relevance measures how well the answer addresses the main aspects of the question, based on the context. Consider whether all and only the important aspects are contained in the answer when evaluating relevance. Given the context and question, score the relevance of the answer between one to five stars using the following rating scale:
One star: the answer completely lacks relevance
Two stars: the answer mostly lacks relevance
Three stars: the answer is partially relevant
Four stars: the answer is mostly relevant
Five stars: the answer has perfect relevance

This rating value should always be an integer between 1 and 5. So the rating produced should be 1 or 2 or 3 or 4 or 5.

context: Marie Curie was a Polish-born physicist and chemist who pioneered research on radioactivity and was the first woman to win a Nobel Prize.
question: What field did Marie Curie excel in?
answer: Marie Curie was a renowned painter who focused mainly on impressionist styles and techniques.
stars: 1

context: The Beatles were an English rock band formed in Liverpool in 1960, and they are widely regarded as the most influential music band in history.
question: Where were The Beatles formed?
answer: The band The Beatles began their journey in London, England, and they changed the history of music.
stars: 2

context: The recent Mars rover, Perseverance, was launched in 2020 with the main goal of searching for signs of ancient life on Mars. The rover also carries an experiment called MOXIE, which aims to generate oxygen from the Martian atmosphere.
question: What are the main goals of Perseverance Mars rover mission?
answer: The Perseverance Mars rover mission focuses on searching for signs of ancient life on Mars.
stars: 3

context: The Mediterranean diet is a commonly recommended dietary plan that emphasizes fruits, vegetables, whole grains, legumes, lean proteins, and healthy fats. Studies have shown that it offers numerous health benefits, including a reduced risk of heart disease and improved cognitive health.
question: What are the main components of the Mediterranean diet?
answer: The Mediterranean diet primarily consists of fruits, vegetables, whole grains, and legumes.
stars: 4

context: The Queen's Royal Castle is a well-known tourist attraction in the United Kingdom. It spans over 500 acres and contains extensive gardens and parks. The castle was built in the 15th century and has been home to generations of royalty.
question: What are the main attractions of the Queen's Royal Castle?
answer: The main attractions of the Queen's Royal Castle are its expansive 500-acre grounds, extensive gardens, parks, and the historical castle itself, which dates back to the 15th century and has housed generations of royalty.
stars: 5

context: {context}
question: {question}
answer: {answer}
stars:"""

gpt_groundedness_prompt_sys = """You are an AI assistant. You will be given the definition of an evaluation metric for assessing the quality of an answer in a question-answering task. Your job is to compute an accurate evaluation score using the provided evaluation metric."""
gpt_groundedness_prompt_user = """
You will be presented with a CONTEXT and an ANSWER about that CONTEXT. You need to decide whether the ANSWER is entailed by the CONTEXT by choosing one of the following rating:
Five stars: The ANSWER follows logically from the information contained in the CONTEXT.
One stars: The ANSWER is logically false from the information contained in the CONTEXT.
an integer score between 1 and 5 and if such integer score does not exist, use One stars: It is not possible to determine whether the ANSWER is true or false without further information. Read the passage of information thoroughly and select the correct answer from the three answer labels. Read the CONTEXT thoroughly to ensure you know what the CONTEXT entails. Note the ANSWER is generated by a computer system, it can contain certain symbols, which should not be a negative factor in the evaluation.

Reminder: The return values for each task should be correctly formatted as an integer between 1 and 5. Do not repeat the context and question.

CONTEXT: Some are reported as not having been wanted at all.,
ANSWER: All are reported as being completely and fully wanted.
STARS: 1

CONTEXT: Ten new television shows appeared during the month of September. Five of the shows were sitcoms, three were hourlong dramas, and two were news-magazine shows. By January, only seven of these new shows were still on the air. Five of the shows that remained were sitcoms.
ANSWER: At least one of the shows that were cancelled was an hourlong drama.
STARS: 5

CONTEXT: In Quebec, an allophone is a resident, usually an immigrant, whose mother tongue or home language is neither French nor English.
ANSWER: In Quebec, an allophone is a resident, usually an immigrant, whose mother tongue or home language is not French.
STARS: 5

CONTEXT: Some are reported as not having been wanted at all.
ANSWER: All are reported as being completely and fully wanted.
STARS: 1

CONTEXT: {context}
ANSWER: {answer}
STARS:"""

gpt_similarity_prompt_sys = """You are an AI assistant. You will be given the definition of an evaluation metric for assessing the quality of an answer in a question-answering task. Your job is to compute an accurate evaluation score using the provided evaluation metric."""
gpt_similarity_prompt_user = """
Equivalence, as a metric, measures the similarity between the predicted answer and the correct answer. If the information and content in the predicted answer is similar or equivalent to the correct answer, then the value of the Equivalence metric should be high, else it should be low. Given the question, correct answer, and predicted answer, determine the value of Equivalence metric using the following rating scale:
One star: the predicted answer is not at all similar to the correct answer
Two stars: the predicted answer is mostly not similar to the correct answer
Three stars: the predicted answer is somewhat similar to the correct answer
Four stars: the predicted answer is mostly similar to the correct answer
Five stars: the predicted answer is completely similar to the correct answer

This rating value should always be an integer between 1 and 5. So the rating produced should be 1 or 2 or 3 or 4 or 5.

The examples below show the Equivalence score for a question, a correct answer, and a predicted answer.

question: What is the role of ribosomes?
correct answer: Ribosomes are cellular structures responsible for protein synthesis. They interpret the genetic information carried by messenger RNA (mRNA) and use it to assemble amino acids into proteins.
predicted answer: Ribosomes participate in carbohydrate breakdown by removing nutrients from complex sugar molecules.
stars: 1

question: Why did the Titanic sink?
correct answer: The Titanic sank after it struck an iceberg during its maiden voyage in 1912. The impact caused the ship's hull to breach, allowing water to flood into the vessel. The ship's design, lifeboat shortage, and lack of timely rescue efforts contributed to the tragic loss of life.
predicted answer: The sinking of the Titanic was a result of a large iceberg collision. This caused the ship to take on water and eventually sink, leading to the death of many passengers due to a shortage of lifeboats and insufficient rescue attempts.
stars: 2

question: What causes seasons on Earth?
correct answer: Seasons on Earth are caused by the tilt of the Earth's axis and its revolution around the Sun. As the Earth orbits the Sun, the tilt causes different parts of the planet to receive varying amounts of sunlight, resulting in changes in temperature and weather patterns.
predicted answer: Seasons occur because of the Earth's rotation and its elliptical orbit around the Sun. The tilt of the Earth's axis causes regions to be subjected to different sunlight intensities, which leads to temperature fluctuations and alternating weather conditions.
stars: 3

question: How does photosynthesis work?
correct answer: Photosynthesis is a process by which green plants and some other organisms convert light energy into chemical energy. This occurs as light is absorbed by chlorophyll molecules, and then carbon dioxide and water are converted into glucose and oxygen through a series of reactions.
predicted answer: In photosynthesis, sunlight is transformed into nutrients by plants and certain microorganisms. Light is captured by chlorophyll molecules, followed by the conversion of carbon dioxide and water into sugar and oxygen through multiple reactions.
stars: 4

question: What are the health benefits of regular exercise?
correct answer: Regular exercise can help maintain a healthy weight, increase muscle and bone strength, and reduce the risk of chronic diseases. It also promotes mental well-being by reducing stress and improving overall mood.
predicted answer: Routine physical activity can contribute to maintaining ideal body weight, enhancing muscle and bone strength, and preventing chronic illnesses. In addition, it supports mental health by alleviating stress and augmenting general mood.
stars: 5

question: {question}
correct answer:{ground_truth}
predicted answer: {answer}
stars:"""

gpt_fluency_prompt_sys = """You are an AI assistant. You will be given the definition of an evaluation metric for assessing the quality of an answer in a question-answering task. Your job is to compute an accurate evaluation score using the provided evaluation metric."""
gpt_fluency_prompt_user = """
Fluency measures the quality of individual sentences in the answer, and whether they are well-written and grammatically correct. Consider the quality of individual sentences when evaluating fluency. Given the question and answer, score the fluency of the answer between one to five stars using the following rating scale:
One star: the answer completely lacks fluency
Two stars: the answer mostly lacks fluency
Three stars: the answer is partially fluent
Four stars: the answer is mostly fluent
Five stars: the answer has perfect fluency

This rating value should always be an integer between 1 and 5. So the rating produced should be 1 or 2 or 3 or 4 or 5.

question: What did you have for breakfast today?
answer: Breakfast today, me eating cereal and orange juice very good.
stars: 1

question: How do you feel when you travel alone?
answer: Alone travel, nervous, but excited also. I feel adventure and like its time.
stars: 2

question: When was the last time you went on a family vacation?
answer: Last family vacation, it took place in last summer. We traveled to a beach destination, very fun.
stars: 3

question: What is your favorite thing about your job?
answer: My favorite aspect of my job is the chance to interact with diverse people. I am constantly learning from their experiences and stories.
stars: 4

question: Can you describe your morning routine?
answer: Every morning, I wake up at 6 am, drink a glass of water, and do some light stretching. After that, I take a shower and get dressed for work. Then, I have a healthy breakfast, usually consisting of oatmeal and fruits, before leaving the house around 7:30 am.
stars: 5

question: {question}
answer: {answer}
stars:"""

# Load environment's settings
load_dotenv()

client = AsyncAzureOpenAI(
    api_key=os.getenv("AZURE_OPENAI_API_KEY"),
    api_version=os.getenv("AZURE_OPENAI_API_VERSION"),
    azure_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
)

async def execute_eval(row_dict):
    tasks = {}
    results = {}
    gpt_relevance = 1
    gpt_groundedness = 1
    gpt_similarity = 1
    gpt_fluency = 1
    ada_cosine_similarity_score = 1

    try:
        if len(row_dict["answer"])>0:
            tasks["gpt_similarity"] = asyncio.create_task(
                chat_completion(gpt_similarity_prompt_sys, gpt_similarity_prompt_user.format(question=row_dict["question"], ground_truth=row_dict["ground_truth"],answer=row_dict["answer"]))
            )
            tasks["gpt_fluency"] = asyncio.create_task(
                chat_completion(gpt_fluency_prompt_sys, gpt_fluency_prompt_user.format(question=row_dict["question"],answer=row_dict["answer"]))
            )
        if len(row_dict["answer"])>0 and len(row_dict["context"])>0:
            tasks["gpt_relevance"] = asyncio.create_task(
                chat_completion(gpt_relevance_prompt_sys, gpt_relevance_prompt_user.format(question=row_dict["question"], context=row_dict["context"],answer=row_dict["answer"]))
            )
            tasks["gpt_groundedness"] = asyncio.create_task(
                chat_completion(gpt_groundedness_prompt_sys, gpt_groundedness_prompt_user.format(context=row_dict["context"],answer=row_dict["answer"]))
            )
        if len(row_dict["ground_truth"])>0 and len(row_dict["answer"])>0:
            tasks["embeddings_gt"] = asyncio.create_task(
                aget_embeddings(row_dict["ground_truth"])
            )
            tasks["embeddings_ans"] = asyncio.create_task(
                aget_embeddings(row_dict["answer"])
            )

        results = await asyncio.gather(*tasks.values())
        results = dict(zip(tasks.keys(), results))

        if "gpt_similarity" in results:
            gpt_similarity = int(results["gpt_similarity"])
        if "gpt_fluency" in results:
            gpt_fluency = int(results["gpt_fluency"])
        if "gpt_relevance" in results:
            gpt_relevance = int(results["gpt_relevance"])
        if "gpt_groundedness" in results:
            gpt_groundedness = int(results["gpt_groundedness"])
        if "embeddings_gt" in results and "embeddings_ans" in results:
            ada_cosine_similarity_score = cosine_similarity_to_bin(calc_cosine_similarity(results["embeddings_gt"][0], results["embeddings_ans"][0]))

    except ValueError as e:
        print("ValueError:", e)
        pass
    
    return {"gpt_relevance": gpt_relevance, "gpt_groundedness": gpt_groundedness, "gpt_similarity": gpt_similarity, "gpt_fluency": gpt_fluency, "ada_cosine_similarity": ada_cosine_similarity_score}

async def _execute_eval_test(row_dict):
    string_list = [1, 2, 3, 4, 5]
    gpt_relevance = random.choice(string_list)
    gpt_groundedness = random.choice(string_list)
    gpt_similarity = random.choice(string_list)
    gpt_fluency = random.choice(string_list)
    ada_cosine_similarity_score = random.choice(string_list)
    print(row_dict["ground_truth"])
    print(row_dict["answer"])
    print(row_dict["context"])
    print(row_dict["question"])

    await asyncio.sleep(random.uniform(1.0, 2.0))

    return {"gpt_relevance": gpt_relevance, "gpt_groundedness": gpt_groundedness, "gpt_similarity": gpt_similarity, "gpt_fluency": gpt_fluency, "ada_cosine_similarity": ada_cosine_similarity_score}


@retry(wait=wait_random_exponential(min=1, max=60), stop=stop_after_attempt(6))
async def chat_completion(system, user):
    try:
        response = await client.chat.completions.create(
            model=os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME"),
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            max_tokens=10,
            temperature=0.0,
        )

    except Exception as e:
        print(e)
        raise
        
    print("chat_completion: ",response.choices[0].message.content)
    return response.choices[0].message.content.strip()[:1]

async def _chat_completion_test(system, user):
    try:
        await asyncio.sleep(random.uniform(1.0, 2.0))
    except Exception as e:
        print(e)
        raise
    # print("chat_completion: ",response.choices[0].message.content)
    string_list = ['1', '2', '3', '4', '5']
    return random.choice(string_list)

@retry(wait=wait_random_exponential(min=1, max=60), stop=stop_after_attempt(6))
def generate_embeddings(text, model=os.getenv("AZURE_OPENAI_EMBED_DEPLOYMENT_NAME")):
    return client.embeddings.create(input = [text], model=model).data[0].embedding

@retry(wait=wait_random_exponential(min=1, max=60), stop=stop_after_attempt(6))
async def aget_embeddings(text, model=os.getenv("AZURE_OPENAI_EMBED_DEPLOYMENT_NAME")):
    data = (
        await client.embeddings.create(input=[text], model=model)
    ).data
    return [d.embedding for d in data]

def calc_cosine_similarity(v1, v2):
    dot_product = np.dot(v1, v2)
    norm_v1 = np.linalg.norm(v1)
    norm_v2 = np.linalg.norm(v2)
    cos = dot_product / (norm_v1 * norm_v2)
    return cos

def cosine_similarity_to_bin(cosine_similarity):
    # コサイン類似度の値が指定された範囲外の場合はエラーを投げる
    if cosine_similarity < 0 or cosine_similarity > 1:
        raise ValueError("コサイン類似度は0から1の範囲内でなければなりません。")
    
    # コサイン類似度値をビンに分類
    if cosine_similarity < 0.2:
        return 1
    elif cosine_similarity < 0.4:
        return 2
    elif cosine_similarity < 0.6:
        return 3
    elif cosine_similarity < 0.8:
        return 4
    else:  # 0.8以上1以下
        return 5

# タイトルの設定
st.title('AI Challenge Day GPT Evaluator')

# ファイルアップロードのセクション
uploaded_file = st.file_uploader("Upload a CSV file.", type=['csv'])

# セッション状態の初期化
if 'data' not in st.session_state:
    st.session_state['data'] = None
if 'result' not in st.session_state:
    st.session_state['result'] = None
if 'count' not in st.session_state:
    st.session_state['count'] = None

# データ処理関数
async def process_csv(data):
    # 進捗バーの初期化
    progress_bar = st.progress(0)
    status_text = st.empty()
    status1 = st.status("Evaluating...", expanded=True)
    # 処理済みデータを格納するリスト
    processed_data = []

    # データ行数
    total_rows = len(data)
    record = {"gpt_relevance": 0, "gpt_groundedness": 0, "gpt_similarity": 0, "gpt_fluency": 0, "ada_cosine_similarity": 0}
    st.session_state['count'] = total_rows

    # 各行ごとに処理
    for i, row in data.iterrows():
        # ステータスの更新
        status_text.text(f'Evaluating: {i + 1}/{total_rows} rows')

        # 行のデータを処理
        processed_row = await execute_eval(row)
        processed_data.append(processed_row)
        #time.sleep(1)
        status1.write(processed_row)
        # 進捗バーの更新
        progress_bar.progress((i + 1) / total_rows)

        # return_score の各キーに対して、record の対応するキーの値に加算
        for key, value in processed_row.items():
            if key in record:
                record[key] += value

    # ステータスのクリア
    status_text.text('Evaluation complete')
    status1.update(label="Evaluation complete!", state="complete", expanded=False)
    return record

# main coroutine
async def main():
    # 非同期処理の実行
    st.session_state['result'] = await process_csv(st.session_state['data'])


if uploaded_file is not None:
    # CSVファイルの読み込み
    data = pd.read_csv(uploaded_file)
    st.session_state['data'] = data.replace(np.nan, '', regex=True)
    st.write(st.session_state['data'])
    # OKボタンを設置
    if st.button('Start evaluation', type="primary"):
        # CSVデータの処理
        asyncio.run(main())

# クリアボタン
if st.button('Clear'):
    # 解析結果とアップロードファイルのセッション状態をクリア
    st.session_state['data'] = None
    st.session_state['result'] = None
    st.session_state['count'] = None
    # ファイルアップローダーのキャッシュをクリア
    st.experimental_rerun()

# 解析結果の表示
if st.session_state['result'] is not None:
    # Show result
    st.write('Evaluation result:')
    #st.write(st.session_state['result'])
    record = st.session_state['result']
    record_count = st.session_state['count']
    print("record", record)
    print("count", record_count)

    # record の各キーをレコード数で除算して平均を計算
    if record_count > 0:
        record = {key: round(value / record_count, 3) for key, value in record.items()}

    st.write("average_score:")
    st.write(record)
    # record の値の合計を算出
    total_score = sum(record.values())
    st.write(f"total_score: {total_score:.3f}")