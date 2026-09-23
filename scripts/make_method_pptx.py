#!/usr/bin/env python3
"""Method 섹션 — 편집 가능한 도형·표. 글씨 최소.
   출력: 260923_method_charts.pptx"""
from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE, MSO_CONNECTOR
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR

C = lambda h: RGBColor.from_string(h)
INK, INK2, MUTED, LINE = C('0B0B0B'), C('52514E'), C('898781'), C('C3C2B7')
BLUE, BLUE2, BLUEL = C('1B4F8F'), C('2A78D6'), C('E8F1FC')
TEAL, TEALL, ORANGE, ORANGEL = C('1B9E77'), C('E6F5F0'), C('EB6834'), C('FDECE5')
GREY, GREYL = C('52514E'), C('F0EFEC')

prs = Presentation(); prs.slide_width, prs.slide_height = Inches(13.333), Inches(7.5)
BLANK = prs.slide_layouts[6]

def title(slide, t, sub=None):
    tb = slide.shapes.add_textbox(Inches(.62), Inches(.34), Inches(12.1), Inches(.85))
    tf = tb.text_frame; tf.word_wrap = True
    r = tf.paragraphs[0].add_run(); r.text = t
    r.font.size, r.font.bold, r.font.color.rgb = Pt(24), True, INK
    if sub:
        r2 = tf.add_paragraph().add_run(); r2.text = sub
        r2.font.size, r2.font.color.rgb = Pt(11.5), MUTED

def box(slide, x, y, w, h, head, lines, fill, edge, headsize=14):
    sh = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(x), Inches(y), Inches(w), Inches(h))
    sh.fill.solid(); sh.fill.fore_color.rgb = fill
    sh.line.color.rgb = edge; sh.line.width = Pt(1.5)
    sh.adjustments[0] = 0.06
    tf = sh.text_frame; tf.word_wrap = True; tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    tf.margin_left = tf.margin_right = Emu(91440)
    p = tf.paragraphs[0]; p.alignment = PP_ALIGN.CENTER
    r = p.add_run(); r.text = head
    r.font.size, r.font.bold, r.font.color.rgb = Pt(headsize), True, edge
    for ln in lines:
        p2 = tf.add_paragraph(); p2.alignment = PP_ALIGN.CENTER
        r2 = p2.add_run(); r2.text = ln
        r2.font.size, r2.font.color.rgb = Pt(12.5), INK2
    return sh

def arrow(slide, x1, y1, x2, y2, col=MUTED, w=1.75):
    cn = slide.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, Inches(x1), Inches(y1), Inches(x2), Inches(y2))
    cn.line.color.rgb = col; cn.line.width = Pt(w)
    cn.line._get_or_add_ln().append_tailEnd = None   # 기본 화살표 없음 -> XML 로 추가
    from pptx.oxml.ns import qn
    ln = cn.line._get_or_add_ln()
    te = ln.makeelement(qn('a:tailEnd'), {'type':'triangle','w':'med','len':'med'}); ln.append(te)
    return cn

def table(slide, rows, x, y, w, h, colw=None, fs=12.5):
    tb = slide.shapes.add_table(len(rows), len(rows[0]), Inches(x), Inches(y), Inches(w), Inches(h)).table
    if colw:
        for j, cw in enumerate(colw): tb.columns[j].width = Inches(cw)
    for i, row in enumerate(rows):
        for j, v in enumerate(row):
            c = tb.cell(i, j); c.text = str(v)
            p = c.text_frame.paragraphs[0]
            p.alignment = PP_ALIGN.LEFT if j == 0 else PP_ALIGN.CENTER
            for r in p.runs:
                r.font.size, r.font.bold = Pt(fs), (i == 0)
                r.font.color.rgb = INK if i == 0 else INK2
    return tb

# ============================================ M1. 세 입력, 하나의 파생
s = prs.slides.add_slide(BLANK)
title(s, '세 입력, 하나의 파생', 'placement 를 판단하려면 요구 · 능력 · 정책을 분리해야 한다')
box(s, 0.85, 1.55, 3.5, 1.75, 'Data object', ['계산이 무엇을 요구하나', 'Footprint · Logical R/W · Lifetime'], BLUEL, BLUE)
box(s, 4.92, 1.55, 3.5, 1.75, 'Memory tier', ['티어가 무엇을 제공하나', 'Capacity · B_R · B_W  (B_path)'], GREYL, GREY)
box(s, 8.99, 1.55, 3.5, 1.75, 'Policy', ['무엇을 어디에 둘까', 'Admission · Retention'], TEALL, TEAL)
for cx in (2.60, 6.67, 10.74):
    arrow(s, cx, 3.30, 6.67, 4.05)
box(s, 3.1, 4.15, 7.15, 1.95, 'Derived execution',
    ['Allocated bytes  ≤  Capacity',
     '경계별 Physical traffic   (HBM↔티어, 티어↔compute)',
     'Service time  =  통과 바이트 / 대역폭'], ORANGEL, ORANGE, headsize=15)
nb = s.shapes.add_textbox(Inches(.85), Inches(6.35), Inches(11.6), Inches(.8))
tf = nb.text_frame; tf.word_wrap = True
r = tf.paragraphs[0].add_run()
r.text = '모델 규칙 — 모든 물리 경계를 독립적으로 센다. 한 경계의 감소가 다른 경계의 트래픽을 만들 수 있다.'
r.font.size, r.font.bold, r.font.color.rgb = Pt(14), True, ORANGE

# ============================================ M2. 세 quantity
s = prs.slides.add_slide(BLANK)
title(s, '저장량 · 요구량 · 이동량은 다른 양이다', '같은 logical access 라도 정책과 계층에 따라 physical traffic 이 달라진다')
rows = [['', 'Allocated bytes', 'Logical access', 'Physical traffic'],
        ['무엇을 세나', '어떤 객체가 차지한 공간', '계산이 요구하는 읽기/쓰기', '경계를 실제로 통과한 바이트'],
        ['무엇이 정하나', '정책 (배치 결과)', '모델 구조 (불변)', '정책 + 계층'],
        ['단위', 'GB', 'GB / step', 'GB / step / 경계'],
        ['예: weight 1 GB 를 읽을 때', '티어에 있으면 1 GB 점유', '항상 1 GB', 'HBM 상주 → HBM 1 GB\n티어 상주 → 티어 1 GB, HBM 0\n수요 캐시 미스 → HBM 1 + 티어 쓰기 1']]
t = table(s, rows, .8, 1.6, 11.7, 3.3, colw=[2.5, 2.9, 2.9, 3.4], fs=12)
nb = s.shapes.add_textbox(Inches(.8), Inches(5.3), Inches(11.7), Inches(1.0))
tf = nb.text_frame; tf.word_wrap = True
r = tf.paragraphs[0].add_run()
r.text = 'logical access 는 데이터가 어디 있든 안 바뀐다. 바뀌는 것은 physical traffic 이고, 그것을 바꾸는 것이 정책이다.'
r.font.size, r.font.bold, r.font.color.rgb = Pt(15), True, INK

# ============================================ M3. Data object
s = prs.slides.add_slide(BLANK)
title(s, 'LLM 데이터를 placement 가능한 객체로', 'Llama-3.1-8B, B=8, N=2,048 기준 · 모델이 바뀌면 이 표가 바뀐다')
rows = [['Data object','Footprint','Logical read / step','Logical write / step','Lifetime'],
        ['dense weight','16.06 GB','15.01 GB','0','모델 수명'],
        ['full KV  (요청당)','50.3 MB','50.3 MB','1 MiB','요청 수명'],
        ['prefill activation','4.29 GB','4.29 GB  (1회)','—','층 1회'],
        ['MLA latent','압축 저장','∝ 문맥 L','토큰당','요청 수명'],
        ['recurrent state (SSM)','고정','고정','고정','요청 수명'],
        ['hot expert (MoE)','전체의 일부','라우팅 의존','0','모델 수명']]
table(s, rows, .8, 1.6, 11.7, 3.5, colw=[3.1, 2.0, 2.4, 2.1, 2.1], fs=12.5)
nb = s.shapes.add_textbox(Inches(.8), Inches(5.35), Inches(11.7), Inches(1.3))
tf = nb.text_frame; tf.word_wrap = True
for k, (t_, bold) in enumerate([
    ('상주 1 바이트당 읽기율 R/F 은 weight 와 KV 가 같다 (스텝당 1회). 그래서 상주 가치는 lifetime 이 가른다.', True),
    ('아래 셋은 모델 구조가 정한다 — 같은 하드웨어라도 모델이 바뀌면 배치 답이 바뀐다.', False)]):
    p = tf.paragraphs[0] if k == 0 else tf.add_paragraph()
    r = p.add_run(); r.text = t_
    r.font.size, r.font.bold, r.font.color.rgb = Pt(14 if bold else 12.5), bold, (INK if bold else INK2)

# ============================================ M4. Policy 두 축
s = prs.slides.add_slide(BLANK)
title(s, 'Policy 는 두 결정으로 끝난다', 'Admission = 공간을 줄 것인가 · Retention = 언제까지 둘 것인가')
rows = [['정책','Admission','Retention','HBM 감소','티어 쓰기'],
        ['일반 캐시 (LRU)','전부, 항상','압력 시 축출','−0.77 %','17.16 GB'],
        ['수요 충전 (LIP)','전부, 항상','압력 시 축출 (삽입 위치만 다름)','+18.59 %','13.86 GB'],
        ['미스에 비할당 + 즉시 반환','차면 그만','해제 신호 오면 즉시','+18.59 %','0'],
        ['관리 상주 (상한)','weight 만','축출 없음','+18.59 %','0']]
table(s, rows, .8, 1.65, 11.7, 2.6, colw=[3.3, 2.0, 3.4, 1.5, 1.5], fs=12.5)
nb = s.shapes.add_textbox(Inches(.8), Inches(4.5), Inches(11.7), Inches(2.0))
tf = nb.text_frame; tf.word_wrap = True
for k, (t_, col, bold, sz) in enumerate([
    ('네 정책은 같은 데이터 · 같은 메모리 · 같은 용량에서 π 만 다르다.', INK, True, 15),
    ('LRU → LIP : retention 만 바꿔도 HBM 감소가 −0.77 → +18.59 %', INK2, False, 13),
    ('LIP → 비할당 : admission 을 바꾸니 같은 감소를 티어 쓰기 0 으로 얻는다', ORANGE, True, 14),
    ('비할당 → 관리 상주 : 주기 장부에서는 같다. 요청 회전이 있어야 갈린다', INK2, False, 13)]):
    p = tf.paragraphs[0] if k == 0 else tf.add_paragraph()
    r = p.add_run(); r.text = ('· ' if k else '') + t_
    r.font.size, r.font.bold, r.font.color.rgb = Pt(sz), bold, col

out = '/Users/choeseoyeon/Desktop/DSIL/2026/09/260923_method_charts.pptx'
prs.save(out); print('저장:', out)
