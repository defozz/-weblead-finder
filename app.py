import re
from datetime import datetime, timezone
from html import unescape
from urllib.parse import urlparse

import feedparser
import pandas as pd
import requests
import streamlit as st

st.set_page_config(page_title="WebLead Finder", page_icon="🎯", layout="wide")
st.markdown("""<style>.block-container{padding-top:1.5rem}.stApp{font-family:system-ui}div[data-testid='stMetric']{background:#f3f6fa;padding:14px;border-radius:12px}</style>""", unsafe_allow_html=True)

FEEDS = {
    "Создание сайтов": "https://freelancehunt.com/projects/skill/sozdanie-sayta-pod-klyuch/96.html.rss",
    "Дизайн сайтов": "https://freelancehunt.com/projects/skill/dizayn-saytov/43.html.rss",
    "Все проекты": "https://freelancehunt.com/projects.rss",
}
KEYWORDS = ["сайт", "лендинг", "landing", "website", "wordpress", "веб", "web", "магазин", "shopify", "tilda", "woocommerce", "редизайн", "створити сайт", "розробка сайту", "інтернет-магазин", "односторінков", "верстк"]
BAD = ["вакансия", "вакансія", "на постоянную работу", "full-time", "seo продвижение", "seo просування"]

@st.cache_data(ttl=600, show_spinner=False)
def load_feed(name, url):
    headers = {"User-Agent": "Mozilla/5.0 (compatible; WebLeadFinder/1.0; feed reader)"}
    response = requests.get(url, headers=headers, timeout=18)
    response.raise_for_status()
    parsed = feedparser.parse(response.content)
    if parsed.bozo and not parsed.entries:
        raise ValueError(f"RSS не удалось прочитать: {parsed.bozo_exception}")
    items = []
    for e in parsed.entries:
        link = e.get('link','').strip()
        if not link or urlparse(link).scheme not in ('https','http'):
            continue
        body = re.sub(r'<[^>]*>', ' ', e.get('summary',''))
        title = unescape(e.get('title','')).strip()
        description = re.sub(r'\s+', ' ', unescape(body)).strip()
        timestamp = e.get('published_parsed') or e.get('updated_parsed')
        date = datetime(*timestamp[:6],tzinfo=timezone.utc) if timestamp else None
        items.append({'Заголовок':title,'Описание':description,'Ссылка':link,'Дата':date,'Источник':name})
    return items

def rank(item):
    text = (item['Заголовок']+' '+item['Описание']).lower()
    score = sum(3 if word in item['Заголовок'].lower() else 1 for word in KEYWORDS if word in text)
    if any(word in text for word in BAD): score -= 3
    if any(word in text for word in ['лендинг', 'landing', 'односторінков', 'сайт-візитка', 'сайт визитка']): score += 3
    return score

st.title('🎯 WebLead Finder')
st.caption('Мониторинг публичных заказов на сайты. Работает с телефона после публикации в Streamlit Community Cloud.')
with st.sidebar:
    st.header('Настройки')
    source_names=st.multiselect('RSS-источники', list(FEEDS), default=list(FEEDS)[:2])
    query=st.text_input('Ключевое слово', placeholder='например: кафе, WordPress, лендинг')
    min_score=st.slider('Минимальная релевантность', 0, 12, 2)
    only_recent=st.selectbox('Давность', ['Любая','Последние 3 дня','Последние 7 дней','Последние 30 дней'], index=2)
    st.caption('Сервис не отправляет сообщения и не собирает персональные данные.')

if not source_names:
    st.info('Выбери хотя бы один источник в меню слева.')
    st.stop()

results=[]
errors=[]
with st.spinner('Загружаю публичные объявления…'):
    for name in source_names:
        try: results.extend(load_feed(name,FEEDS[name]))
        except Exception as e: errors.append(f'{name}: {e}')

unique={}
for r in results:
    unique[r['Ссылка'].split('?')[0]]=r
results=list(unique.values())
for r in results: r['Релевантность']=rank(r)
results=[r for r in results if r['Релевантность']>=min_score and (not query or query.lower() in (r['Заголовок']+' '+r['Описание']).lower())]
max_age={'Любая':None, 'Последние 3 дня':3, 'Последние 7 дней':7, 'Последние 30 дней':30}[only_recent]
if max_age is not None:
    now=datetime.now(timezone.utc)
    results=[r for r in results if r['Дата'] and 0 <= (now-r['Дата']).total_seconds() <= max_age*86400]
results.sort(key=lambda r:(r['Релевантность'], r['Дата'] or datetime(1970,1,1,tzinfo=timezone.utc)),reverse=True)

for error in errors: st.warning(f'Источник временно недоступен — {error}')
if not results:
    st.info('Заказов по текущим фильтрам нет. Попробуй выбрать «Любая» давность, снизить релевантность или включить «Все проекты».')
else:
    st.metric('Найдено подходящих заказов',len(results))
    st.caption('Объявления могут закрываться после публикации. Проверяй статус на бирже.')
    if 'lead_status' not in st.session_state:
        st.session_state.lead_status = {}
    for r in results[:100]:
        date=r['Дата'].strftime('%d.%m.%Y') if r['Дата'] else 'не указана'
        with st.container(border=True):
            st.markdown(f"**{r['Заголовок']}**")
            st.caption(f"{r['Источник']} · {date} · Релевантность: {r['Релевантность']}")
            st.write((r['Описание'][:360]+'…') if len(r['Описание'])>360 else r['Описание'])
            st.link_button('Открыть заказ ↗',r['Ссылка'])
            options=['Новый','Написал','Не подходит']
            saved=st.session_state.lead_status.get(r['Ссылка'],'Новый')
            status=st.selectbox('Статус', options, index=options.index(saved), key='status_'+str(abs(hash(r['Ссылка']))))
            st.session_state.lead_status[r['Ссылка']]=status
    export=pd.DataFrame([{**r,'Дата':r['Дата'].isoformat() if r['Дата'] else '', 'Статус':st.session_state.lead_status.get(r['Ссылка'],'Новый')} for r in results])
    st.download_button('⬇ Скачать результаты CSV',export.to_csv(index=False).encode('utf-8-sig'),file_name='website_leads.csv',mime='text/csv')

st.divider()
st.subheader('Быстрый отклик')
st.code('Доброго дня! Побачив ваше завдання щодо сайту. Можу розробити адаптивний сайт із сучасним дизайном. Підкажіть, будь ласка, чи є приклади сайтів, які вам подобаються, та який орієнтовний бюджет?',language=None)
st.caption('Используй только в рамках правил площадки. Не отправляй массовые одинаковые сообщения.')
