#!/usr/bin/env python3
"""Problem 섹션 그림을 네이티브 PowerPoint 차트로. 글씨 최소, 주석 없음, 축 제목 있음.
   출력: 260923_problem_charts.pptx"""
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.chart.data import CategoryChartData, XyChartData
from pptx.enum.chart import (XL_CHART_TYPE, XL_LEGEND_POSITION, XL_TICK_MARK,
                             XL_TICK_LABEL_POSITION, XL_MARKER_STYLE, XL_LABEL_POSITION)
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN

C = lambda h: RGBColor.from_string(h)
INK, INK2, MUTED, GRID, AXIS = C('0B0B0B'), C('52514E'), C('898781'), C('E8E7E1'), C('C3C2B7')
BLUE, BLUE2, BLUE3, BLUE4 = C('1B4F8F'), C('2A78D6'), C('7DB0E8'), C('B9D3F2')
ORANGE, TEAL = C('EB6834'), C('1B9E77')

prs = Presentation(); prs.slide_width, prs.slide_height = Inches(13.333), Inches(7.5)
BLANK = prs.slide_layouts[6]

def title(slide, text, sub=None):
    tb = slide.shapes.add_textbox(Inches(.62), Inches(.34), Inches(12.1), Inches(.85))
    tf = tb.text_frame; tf.word_wrap = True
    r = tf.paragraphs[0].add_run(); r.text = text
    r.font.size, r.font.bold, r.font.color.rgb = Pt(24), True, INK
    if sub:
        r2 = tf.add_paragraph().add_run(); r2.text = sub
        r2.font.size, r2.font.color.rgb = Pt(11.5), MUTED

def axis_title(ax, text, size=12):
    ax.has_title = True
    tf = ax.axis_title.text_frame; tf.text = text
    for r in tf.paragraphs[0].runs:
        r.font.size, r.font.bold, r.font.color.rgb = Pt(size), False, INK2

def quiet(chart, xt, yt, legend=True, pos=XL_LEGEND_POSITION.BOTTOM):
    chart.has_title = False
    chart.has_legend = legend
    if legend:
        chart.legend.position = pos; chart.legend.include_in_layout = False
        chart.legend.font.size = Pt(12); chart.legend.font.color.rgb = INK2
    for ax, t in ((chart.category_axis, xt), (chart.value_axis, yt)):
        ax.tick_labels.font.size = Pt(12); ax.tick_labels.font.color.rgb = INK2
        ax.major_tick_mark = XL_TICK_MARK.NONE; ax.minor_tick_mark = XL_TICK_MARK.NONE
        ax.format.line.color.rgb = AXIS
        if t: axis_title(ax, t)
    chart.value_axis.has_major_gridlines = True
    gl = chart.value_axis.major_gridlines.format.line
    gl.color.rgb = GRID; gl.width = Pt(0.75)
    chart.category_axis.has_major_gridlines = False

def style_line(ser, rgb, width=2.5, dash=None, marker=True, msize=7):
    ser.format.line.color.rgb = rgb; ser.format.line.width = Pt(width); ser.smooth = False
    if dash: ser.format.line.dash_style = dash
    if marker:
        ser.marker.style = XL_MARKER_STYLE.CIRCLE; ser.marker.size = msize
        ser.marker.format.fill.solid(); ser.marker.format.fill.fore_color.rgb = rgb
        ser.marker.format.line.color.rgb = rgb
    else:
        ser.marker.style = XL_MARKER_STYLE.NONE

def bar_color(ser, rgb):
    ser.invert_if_negative = False
    ser.format.fill.solid(); ser.format.fill.fore_color.rgb = rgb
    ser.format.line.fill.background()

# ================================================== 1. 용량 x 정책
s = prs.slides.add_slide(BLANK)
title(s, '같은 용량, 다른 정책', '통일 장부 정확 재생 · 20개 설계 셀 · 티어 용량은 면적에 비례')
d = CategoryChartData(); d.categories = ['400','500','600','700','800']
d.add_series('C2 2층', (12.00,15.00,18.00,21.00,24.00))
d.add_series('C3 2층', (7.92,9.90,11.88,13.86,15.84))
d.add_series('C2 1층', (6.00,7.50,9.00,10.50,12.00))
d.add_series('C3 1층', (3.96,4.95,5.94,6.93,7.92))
d.add_series('일반 캐시 (LRU) — 전 셀 동일', (-0.7455,)*5)
ch = s.shapes.add_chart(XL_CHART_TYPE.LINE_MARKERS, Inches(.75), Inches(1.5), Inches(11.8), Inches(5.35), d).chart
quiet(ch, '순배치 면적  [mm² / die / layer]', 'HBM 물리 트래픽 감소  [%]')
for ser, col, w, m in zip(ch.series, (BLUE, BLUE2, BLUE3, BLUE4, INK), (3.25,2.25,2.25,2.25,3.0), (8,6,6,6,0)):
    style_line(ser, col, w, marker=bool(m), msize=m or 6)
ch.series[4].format.line.dash_style = 4
va = ch.value_axis; va.minimum_scale, va.maximum_scale, va.major_unit = -5, 25, 5
ch.category_axis.tick_label_position = XL_TICK_LABEL_POSITION.LOW

# ================================================== 2. 경계별 트래픽
s = prs.slides.add_slide(BLANK)
title(s, '경계별 트래픽', '600 mm², C2 2층 · 정상 상태 = 마지막 스텝 · HBM 만 세면 LIP 가 좋아 보인다')
d = CategoryChartData()
d.categories = ['일반 캐시\n(LRU)','수요 충전\n(LIP)','미스에 비할당\n+ 즉시 반환','관리 상주\n(상한)']
d.add_series('HBM 읽기',        (17.158, 13.862, 13.861, 13.861))
d.add_series('티어 읽기',        (0.000, 3.296, 3.297, 3.297))
d.add_series('티어 쓰기 (충전)', (17.157, 13.862, 0.000, 0.000))
ch = s.shapes.add_chart(XL_CHART_TYPE.COLUMN_CLUSTERED, Inches(.75), Inches(1.5), Inches(11.8), Inches(5.35), d).chart
quiet(ch, '', '트래픽  [GB / decode step]', pos=XL_LEGEND_POSITION.TOP)
for ser, col in zip(ch.series, (BLUE2, TEAL, ORANGE)): bar_color(ser, col)
ch.plots[0].gap_width, ch.plots[0].overlap = 70, -8
for ser in ch.series:
    ser.data_labels.show_value = True
    dl = ser.data_labels; dl.font.size = Pt(10.5); dl.font.color.rgb = INK2
    dl.number_format, dl.number_format_is_linked = '0.00', False
    dl.position = XL_LABEL_POSITION.OUTSIDE_END
ch.value_axis.minimum_scale, ch.value_axis.maximum_scale = 0, 20

# ================================================== 3. 요구 쓰기 대역폭
s = prs.slides.add_slide(BLANK)
title(s, '필요한 쓰기 대역폭 vs 있는 대역폭',
      '600 mm², B_R = 19 TB/s · 왼쪽 셋 = 본전에 필요한 값, 오른쪽 둘 = 실제로 줄 수 있는 값')
d = CategoryChartData()
d.categories = ['수요 충전 (LIP)\n직렬 경계','수요 충전 (LIP)\n겹침 경계','미스에 비할당\n+ 즉시 반환',
                '소자팀 덱\nlike-for-like','패브릭 상한\nL2 → SM']
d.add_series('TB/s', (43.18, 5.57, 0.0, 17.7, 19.0))
ch = s.shapes.add_chart(XL_CHART_TYPE.COLUMN_CLUSTERED, Inches(1.0), Inches(1.6), Inches(11.3), Inches(5.25), d).chart
quiet(ch, '', '쓰기 대역폭  [TB/s]', legend=False)
ser = ch.series[0]; ch.plots[0].gap_width = 90
for i, col in enumerate((BLUE2, BLUE2, TEAL, MUTED, MUTED)):
    pt = ser.points[i]; pt.format.fill.solid(); pt.format.fill.fore_color.rgb = col
    pt.format.line.fill.background()
ser.data_labels.show_value = True
dl = ser.data_labels
dl.font.size, dl.font.bold, dl.font.color.rgb = Pt(15), True, INK
dl.number_format, dl.number_format_is_linked = '0.00', False
dl.position = XL_LABEL_POSITION.OUTSIDE_END
ch.value_axis.minimum_scale, ch.value_axis.maximum_scale, ch.value_axis.major_unit = 0, 48, 8

# ================================================== 4. 숙제
s = prs.slides.add_slide(BLANK)
title(s, '용량을 쓰려면 필요한 L2 대역폭', 'B_min(C) = B_HBM / (1 − C/D) · D = 17.157 GB/step, B_HBM = 6.40 TB/s')
xy = XyChartData()
sr = xy.add_series('필요 최소 대역폭')
for c in [0.13,0.5,1,1.5,2,3,4.22,5,6,7,8,9,10,11,11.38,12,12.5,13,13.5,14]:
    sr.add_data_point(c, 6.40/(1-c/17.157))
sr2 = xy.add_series('B200 L2 실측 19 TB/s')
for c in (0.13, 14): sr2.add_data_point(c, 19.0)
ch = s.shapes.add_chart(XL_CHART_TYPE.XY_SCATTER_LINES_NO_MARKERS, Inches(.9), Inches(1.5), Inches(11.5), Inches(5.35), xy).chart
quiet(ch, 'L2 용량 C  [GB]', '필요 L2 → 프로세서 대역폭  [TB/s]', pos=XL_LEGEND_POSITION.TOP)
style_line(ch.series[0], INK, 3.0, marker=False); ch.series[0].smooth = True
style_line(ch.series[1], ORANGE, 2.0, dash=4, marker=False)
ch.value_axis.minimum_scale, ch.value_axis.maximum_scale, ch.value_axis.major_unit = 0, 60, 10
ch.category_axis.minimum_scale, ch.category_axis.maximum_scale, ch.category_axis.major_unit = 0, 14, 2

# ================================================== 5. 원본 데이터
s = prs.slides.add_slide(BLANK)
title(s, '원본 데이터', '차트를 다시 그릴 때 쓰는 값 · 전부 통일 장부 정확 재생 [trace replay]')
rows = [['정책','HBM 읽기','티어 읽기','티어 쓰기','HBM 감소','본전 B_W 직렬','본전 B_W 겹침'],
        ['일반 캐시 (LRU)','17.158','0.000','17.157','−0.77 %','불가능','6.45'],
        ['수요 충전 (LIP)','13.862','3.296','13.862','+18.59 %','43.18','5.57'],
        ['미스 비할당 + 즉시반환','13.861','3.297','0.000','+18.59 %','요구 없음','요구 없음'],
        ['관리 상주 (상한)','13.861','3.297','0.000','+18.59 %','요구 없음','요구 없음']]
tb = s.shapes.add_table(len(rows), 7, Inches(.75), Inches(1.75), Inches(11.8), Inches(2.5)).table
tb.columns[0].width = Inches(3.0)
for j in range(1, 7): tb.columns[j].width = Inches(1.466)
for i, row in enumerate(rows):
    for j, v in enumerate(row):
        cell = tb.cell(i, j); cell.text = v
        p = cell.text_frame.paragraphs[0]; p.alignment = PP_ALIGN.CENTER if j else PP_ALIGN.LEFT
        for r in p.runs:
            r.font.size, r.font.bold = Pt(12.5), (i == 0)
            r.font.color.rgb = INK if i == 0 else INK2
nb = s.shapes.add_textbox(Inches(.75), Inches(4.45), Inches(11.8), Inches(1.4))
tf = nb.text_frame; tf.word_wrap = True
for k, t in enumerate(['단위 GB / decode step · 정상 상태(마지막 스텝) · 티어 3.164 GB + 기존 L2 0.133 GB',
                       'LRU 의 HBM 은 전체 수요 F+W 와 바이트 단위로 일치 — 적중률이 근사가 아니라 정확히 0',
                       '본전 B_W = speedup 1 이 되는 최소 절대 쓰기 대역폭. 덱 17.7 / 패브릭 19 와 비교할 것']):
    p = tf.paragraphs[0] if k == 0 else tf.add_paragraph()
    r = p.add_run(); r.text = '· ' + t; r.font.size, r.font.color.rgb = Pt(12), INK2

out = '/Users/choeseoyeon/Desktop/DSIL/2026/09/260923_problem_charts.pptx'
prs.save(out); print('저장:', out)
