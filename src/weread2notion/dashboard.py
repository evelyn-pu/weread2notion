"""Private, managed reading dashboard. Never edits the user's journal blocks."""
from datetime import datetime, timedelta, timezone

HOME = '408b852dd984809986aac93be58ebb61'
TITLE = '阅读数据 · 自动更新'
TZ = timezone(timedelta(hours=8))


def rich(text):
    return [{'type': 'text', 'text': {'content': str(text)[:2000]}}]


def block(kind, text):
    return {'object': 'block', 'type': kind, kind: {'rich_text': rich(text)}}


def duration(seconds):
    minutes = int(seconds) // 60
    return f'{minutes // 60}小时{minutes % 60}分'


def children(client, parent):
    result, cursor = [], None
    while True:
        args = {'block_id': parent, 'page_size': 100}
        if cursor:
            args['start_cursor'] = cursor
        response = client.blocks.children.list(**args)
        result.extend(response['results'])
        if not response.get('has_more'):
            return result
        cursor = response['next_cursor']


def render(month, year, overall, now):
    for data in (month, year, overall):
        if not isinstance(data.get('totalReadTime'), (int, float)):
            raise ValueError('阅读统计缺少总时长，停止更新，保留原数据')
    daily = year.get('dailyReadTimes')
    complete = isinstance(daily, dict) and bool(daily)
    source = daily if complete else month.get('readTimes', {})
    days = {datetime.fromtimestamp(int(k), TZ).date(): v for k, v in source.items()}
    today = now.date()
    today_seconds = days.get(today, 0)
    panels = [('今日', duration(today_seconds)), ('本月', duration(month['totalReadTime'])),
              ('本年', duration(year['totalReadTime']))]
    out = [block('paragraph', '此页由微信读书自动更新。原创札记请写在图书馆的独立札记区。'),
           block('paragraph', '更新于 ' + now.strftime('%Y-%m-%d %H:%M') + '（北京时间）')]
    cols = [{'object':'block','type':'column','column':{'children':[
        block('heading_2', name), block('paragraph', value)]}} for name,value in panels]
    out.append({'object':'block','type':'column_list','column_list':{'children':cols}})
    out.append(block('paragraph', '累计阅读／收听：' + duration(overall['totalReadTime']) +
                     ' · 本年有效阅读 ' + str(year.get('readDays', '未提供')) + ' 天'))
    out.append(block('heading_2', f'{now.year} · 阅读热力图'))
    start = datetime(now.year, 1, 1, tzinfo=TZ).date()
    start -= timedelta(days=start.weekday())
    weeks = (today - start).days // 7 + 1
    lines = []
    for weekday, name in enumerate('一二三四五六日'):
        cells = []
        for week in range(weeks):
            day = start + timedelta(days=week*7+weekday)
            if day.year != now.year or day > today:
                cells.append(' ')
            elif not complete and day.month != now.month:
                cells.append('?')
            else:
                seconds = days.get(day, 0)
                cells.append('·' if seconds < 60 else '░' if seconds < 1800 else '▒' if seconds < 3600 else '▓' if seconds < 7200 else '█')
        lines.append(name + ' ' + ''.join(cells))
    out.append({'object':'block','type':'code','code':{'rich_text':rich('\n'.join(lines)), 'language':'plain text'}})
    out.append(block('paragraph', '每列一周，自左向右。· 不满1分钟；░ 1–29分钟；▒ 30–59分钟；▓ 1–2小时；█ 2小时以上。' +
                     ('' if complete else '接口未提供完整年度每日数据，? 表示历史日期未知，不表示没有阅读。')))
    out.append(block('heading_2', '每月阅读时长'))
    monthly = {datetime.fromtimestamp(int(k), TZ).month:v for k,v in (year.get('readTimes') or {}).items()}
    peak = max(monthly.values(), default=0)
    chart = '\n'.join(f'{m:02d}月 ' + ('█' * round(monthly.get(m,0)/peak*20) if peak else '') + ' ' + duration(monthly.get(m,0)) for m in range(1, now.month+1))
    out.append({'object':'block','type':'code','code':{'rich_text':rich(chart),'language':'plain text'}})
    out.append(block('heading_2', '本年阅读最多'))
    ranking = year.get('readLongest') or []
    for row in ranking:
        book = row.get('book') or row.get('albumInfo') or {}
        out.append(block('paragraph', (book.get('title') or book.get('name') or '未命名') + ' · ' + duration(row.get('readTime',0))))
    if not ranking:
        out.append(block('paragraph', '接口尚未提供符合排行条件的书籍。'))
    out.append(block('heading_2', '作者足迹'))
    authors = overall.get('preferAuthor') or []
    for author in authors:
        out.append(block('paragraph', f"{author.get('name','')} · {author.get('count',0)}本 · {author.get('readTime','未提供时长')}"))
    if not authors:
        out.append(block('paragraph', '作者数据尚未达到接口展示条件。'))
    return out


def sync_dashboard(weread, client):
    now = datetime.now(TZ)
    data = [weread.request('/readdata/detail', mode=mode) for mode in ('monthly','annually','overall')]
    content = render(*data, now)
    matches = [b for b in children(client, HOME) if b['type']=='child_page' and b['child_page']['title']==TITLE]
    if len(matches)>1:
        raise ValueError('发现多个自动统计页，请先核对，未修改任何页面')
    if matches:
        page_id = matches[0]['id']
    else:
        page_id = client.pages.create(parent={'page_id':HOME}, properties={'title':{'type':'title','title':rich(TITLE)}})['id']
    previous = children(client, page_id)
    for offset in range(0,len(content),100):
        client.blocks.children.append(block_id=page_id, children=content[offset:offset+100])
    for old in previous:
        client.blocks.delete(block_id=old['id'])
    print('阅读统计和热力图已更新：' + page_id)
