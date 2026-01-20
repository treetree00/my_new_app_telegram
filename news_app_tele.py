import streamlit as st
import requests
from bs4 import BeautifulSoup
import re
from datetime import datetime, timedelta

# 브라우저 탭에 표시될 이름 설정
st.set_page_config(page_title="성훈's News Monitor by Telegram", page_icon="📰")

# --- [1] 사용자 설정 (Secrets 활용) ---
# 텔레그램 설정은 Streamlit Secrets에 TELEGRAM_TOKEN, TELEGRAM_CHAT_ID로 저장하세요.
TELEGRAM_TOKEN = st.secrets.get("TELEGRAM_TOKEN", "사용자님의_봇_토큰")
TELEGRAM_CHAT_ID = st.secrets.get("TELEGRAM_CHAT_ID", "사용자님의_채팅_ID")
NAVER_CLIENT_ID = st.secrets.get("NAVER_ID", "사용자님의_네이버_ID")
NAVER_CLIENT_SECRET = st.secrets.get("NAVER_SECRET", "사용자님의_네이버_시크릿")

# --- [2] 보조 함수 (텔레그램 전송 및 뉴스 로직) ---

def send_telegram(msg):
    """텔레그램 봇을 통해 메시지 전송"""
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        # HTML 태그를 사용하여 메시지를 조금 더 예쁘게 만듭니다.
        payload = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": msg,
            "parse_mode": "HTML",
            "disable_web_page_preview": False
        }
        res = requests.post(url, json=payload)
        return res.status_code == 200
    except Exception as e:
        st.error(f"텔레그램 전송 중 오류: {e}")
        return False

def get_media_by_domain(url):
    domain_map = {'livesnews.com': '라이브뉴스', 'hinews.kr': '하이뉴스', 'mdtoday.co.kr': '메디컬투데이', 'sjbnews.com': '새전북신문', 'jeonmin.co.kr': '전민일보', 'beopbo.com': '법보신문', 'medicalworldnews.co.kr': '메디컬월드뉴스', 'kmedinfo.co.kr': '한국의학정보연구원'}
    low_url = url.lower()
    for domain, name in domain_map.items():
        if domain in low_url: return name
    return None

def shorten_url(url):
    if not url: return ""
    bad_domains = ['sjbnews.com', 'jeonmin.co.kr', 'mdtoday.co.kr', 'hinews.kr', 'livesnews.com']
    if any(d in url.lower() for d in bad_domains): return url
    try:
        res = requests.get(f"https://is.gd/create.php?format=simple&url={url}", timeout=3.0)
        if res.status_code == 200: return res.text.strip()
    except: pass
    return url

def get_real_info(url, title_text=""):
    real_media, real_date = "네이버/daum/google", ""
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
        res = requests.get(url, headers=headers, timeout=5.0)
        if res.status_code == 200:
            res.encoding = res.apparent_encoding
            soup = BeautifulSoup(res.text, 'html.parser')
            if "naver.com" in url:
                m_press = soup.find('meta', property='og:article:author') or soup.find('meta', {'name':'twitter:creator'})
                if m_press: real_media = m_press.get('content', '').split('|')[0].strip()
            elif "daum.net" in url:
                m_press = soup.find('meta', property='article:media_name')
                if m_press: real_media = m_press.get('content', '').strip()
            
            if real_media == "네이버/daum/google":
                d_name = get_media_by_domain(url)
                if d_name: real_media = d_name
                else:
                    meta_site = soup.find('meta', property='og:site_name')
                    if meta_site:
                        name = meta_site.get('content', '').strip()
                        if name and name not in ['네이버 뉴스', '다음뉴스', 'Google News', 'Google', '네이버']: real_media = name
            
            raw_text = res.text
            patterns = [r'(\d{4}[-./]\d{2}[-./]\d{2}).{0,50}?(\d{2}:\d{2})', r'(?:승인|발행|등록|입력|수정).*?(\d{4}[-./]\d{2}[-./]\d{2}).{0,100}?(\d{2}:\d{2})']
            for p in patterns:
                m = re.search(p, raw_text, re.DOTALL)
                if m:
                    real_date = f"{m.group(1).replace('.','-').replace('/','-')} | {m.group(2)}"
                    break
    except: pass
    if real_media == "네이버/daum/google" and " - " in title_text:
        maybe = title_text.split(" - ")[-1].strip()
        if maybe not in ['네이버 뉴스', '다음뉴스', 'Google News']: real_media = maybe
    if "." in real_media: real_media = real_media.replace(".", "․")
    return real_media, real_date

def parse_api_date(date_str):
    if not date_str: return "날짜 정보 없음"
    try:
        if "," in date_str: dt = datetime.strptime(date_str[:25].strip(), "%a, %d %b %Y %H:%M:%S") + timedelta(hours=9)
        else: dt = datetime.fromisoformat(date_str.replace('Z', '+00:00')) + timedelta(hours=9)
        return dt.strftime("%Y-%m-%d | %H:%M")
    except: return "날짜 형식 오류"

def create_report(keywords, days):
    final_items = []
    now_korea = datetime.now() + timedelta(hours=9)
    cutoff = (now_korea - timedelta(days=days)).replace(hour=0, minute=0, second=0, microsecond=0)
    junk_keywords = ['부고', '게시판', '인사', '포토', '알림', '동정', '화보']

    for kw in keywords:
        search_kw = kw if re.sub(r'\s+', '', kw).isalpha() else f'"{kw}"'
        headers = {"X-Naver-Client-Id": NAVER_CLIENT_ID, "X-Naver-Client-Secret": NAVER_CLIENT_SECRET}
        r = requests.get("https://openapi.naver.com/v1/search/news.json", headers=headers, params={"query": search_kw, "display": 100, "sort": "date"})
        raw = [{"title": BeautifulSoup(i["title"], "html.parser").get_text(), "url": i["link"], "api_date": i.get("pubDate")} for i in r.json().get("items", [])]
        
        try:
            google_url = f"https://news.google.com/rss/search?q={search_kw}"
            gr = requests.get(google_url, timeout=10)
            soup = BeautifulSoup(gr.text, "xml")
            raw += [{"title": item.find("title").text, "url": item.find("link").text, "api_date": item.find("pubDate").text} for item in soup.select("item")]
        except: pass

        for item in raw:
            try:
                clean_title = re.sub(r'\s*-\s*[^-]+$', '', item['title']).strip().replace("...", "").replace("…", "").strip()
                is_dup = False
                for x in final_items:
                    if clean_title[:20] == x['title'][:20] or item['url'] in x['url'] or x['url'] in item['url']:
                        is_dup = True; break
                if is_dup: continue
                if "news.google.com" not in item['url'] and kw.lower() not in item['title'].lower(): continue
                if any(junk in item['title'] for junk in junk_keywords): continue

                api_date = parse_api_date(item['api_date'])
                dt_obj = datetime.strptime(api_date.split(" | ")[0], "%Y-%m-%d")
                if dt_obj >= cutoff:
                    media, real_date = get_real_info(item['url'], item['title'])
                    item['media'], item['date'], item['sort_key'], item['title'] = media, (real_date if real_date else api_date), (real_date if real_date else api_date), clean_title
                    final_items.append(item)
            except: continue

    final_items.sort(key=lambda x: x['sort_key'], reverse=True)
    now_str = now_korea.strftime('%Y-%m-%d | %H:%M')
    
    if len(final_items) > 0:
        # 헤더 전송
        header = (
            f"<b>[뉴스 모니터링 결과]</b>\n"
            f"🎯 키워드: {', '.join(keywords)}\n"
            f"🗓️ 기간: {days}일간\n"
            f"📝 총 {len(final_items)}건의 기사"
        )
        send_telegram(header)

        # 개별 기사 전송 (텔레그램은 메시지가 길어도 잘 전송되지만, 가독성을 위해 하나씩 보냅니다)
        for idx, it in enumerate(final_items, 1):
            msg = (
                f"<b>[{idx}] {it['title']}</b>\n"
                f"🗓️ {it['date']} | 📰 {it['media']}\n"
                f"🔗 <a href='{shorten_url(it['url'])}'>기사보기</a>"
            )
            send_telegram(msg)
    
    return {"keywords": ", ".join(keywords), "time": now_str, "days": days, "count": len(final_items)}

# --- [3] 메인 UI 실행부 ---
if __name__ == "__main__":
    st.markdown(
        """
        <div style="text-align: center;">
            <h3 style="margin-bottom: 0px;">🎯 News Monitor (텔레그램)</h3>
            <p style="font-size: 13px; color: grey; margin-top: 5px;">
                Copyright by <span style="color: #1E90FF; font-weight: bold;">성훈</span>
            </p>
        </div>
        """, 
        unsafe_allow_html=True
    )

    st.write("")

    with st.form("search_form"):
        kw_input = st.text_input("키워드(쉼표 구분)", placeholder="예: 올타이트, alltite")
        day_input = st.slider("검색 기간 (일)", 1, 100, 1)
        submit_button = st.form_submit_button("뉴스 검색 및 텔레그램 전송")

    if submit_button and kw_input:
        with st.spinner('뉴스 수집 및 텔레그램 전송 中...'):
            report = create_report([k.strip() for k in kw_input.split(",")], day_input)
            
            if report['count'] > 0:
                st.success(f"✅ 총 {report['count']}건 뉴스, 텔레그램 전송 완료!")
                st.balloons()
            else:
                st.warning("⚠️ 검색된 뉴스 X, 전송 X")
            
            st.markdown("---")
            st.info(f"""
            🎯 **검색 단어** : {report['keywords']}  
            🗓️ **검색 시간** : {report['time']}  
            🗓️ **검색 기간** : {report['days']}일  
            📝 **해당 기사** : 총 {report['count']}건
            """)
