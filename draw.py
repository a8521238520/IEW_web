import matplotlib.pyplot as plt
import matplotlib.patches as patches
from matplotlib.font_manager import FontProperties
import platform
import os


system_name = platform.system() 
font_path = None

   
possible_linux_fonts = [
    '/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc',
    '/usr/share/fonts/truetype/arphic/uming.ttc'
]
for path in possible_linux_fonts:
    if os.path.exists(path):
        font_path = path
        break

if font_path and os.path.exists(font_path):
    print(f"成功載入系統字型：{font_path}")
    my_font = FontProperties(fname=font_path)
else:
    print("找不到系統內建字型，文字可能會變亂碼。")
    my_font = FontProperties()



fig, ax = plt.subplots(figsize=(12, 12))
ax.set_xlim(0, 100)
ax.set_ylim(0, 100)
ax.axis('off')


def draw_box(x, y, w, h, text, color='#E3F2FD', edgecolor='#2196F3', text_color='black', fontsize=13):
    rect = patches.FancyBboxPatch((x, y), w, h, boxstyle="round,pad=1", 
                                  linewidth=1.5, edgecolor=edgecolor, facecolor=color)
    ax.add_patch(rect)
    ax.text(x + w/2, y + h/2, text, ha='center', va='center', 
            fontproperties=my_font, fontsize=fontsize, color=text_color, wrap=True)
    return (x + w/2, y + h/2)

def draw_arrow(start, end):
    ax.annotate("", xy=end, xytext=start,
                arrowprops=dict(arrowstyle="->", color='#555555', lw=1.5))

# ========== 第一階段 ==========
ax.text(5, 96, '第一階段：船類聲音資料收集與標註', fontproperties=my_font, fontsize=18, fontweight='bold', color='#0D47A1')
rect1 = patches.Rectangle((2, 75), 96, 23, linewidth=1, edgecolor='#0D47A1', facecolor='none', linestyle='--')
ax.add_patch(rect1)

p1 = draw_box(35, 88, 30, 4, "資料收集\n(來源 : ShipsEar + 多場域錄音)")
p2 = draw_box(35, 80, 30, 4, "船類聲紋分析和資料標註\n(建立索引)")
p3 = draw_box(35, 72, 30, 4, "水下目標聲紋資料庫\n(訓練/測試集)", color='#B3E5FC')

draw_arrow((p1[0], p1[1]-2.5), (p2[0], p2[1]+2.5))
draw_arrow((p2[0], p2[1]-2.5), (p3[0], p3[1]+2.5))

# ========== 第二階段 ==========
ax.text(5, 68, '第二階段：已知目標類型識別', fontproperties=my_font, fontsize=18, fontweight='bold', color='#1B5E20')
rect2 = patches.Rectangle((2, 35), 46, 35, linewidth=1, edgecolor='#1B5E20', facecolor='none', linestyle='--')
ax.add_patch(rect2)

p4 = draw_box(10, 60, 30, 4, "初版模型(改名)建置與訓練\n(五至七種船類)", color='#E8F5E9', edgecolor='#4CAF50')
p5 = draw_box(10, 50, 30, 4, "資料擴增 & 優化\n(提升至 70-80%)", color='#E8F5E9', edgecolor='#4CAF50')
p6 = draw_box(10, 40, 30, 4, "已知目標識別結果", color='#C8E6C9', edgecolor='#4CAF50')

draw_arrow((p3[0]-5, p3[1]-2.5), (p4[0]+10, p4[1]+2.5)) 
draw_arrow((p4[0], p4[1]-2.5), (p5[0], p5[1]+2.5))
draw_arrow((p5[0], p5[1]-2.5), (p6[0], p6[1]+2.5))

# ========== 第三階段 ==========
ax.text(52, 68, '第三階段：異常目標與行為偵測', fontproperties=my_font, fontsize=18, fontweight='bold', color='#B71C1C')
rect3 = patches.Rectangle((50, 5), 48, 65, linewidth=1, edgecolor='#B71C1C', facecolor='none', linestyle='--')
ax.add_patch(rect3)

p7 = draw_box(59, 60, 30, 4, "異常模擬合成\n(<100Hz 低頻/寬頻)", color='#FFEBEE', edgecolor='#EF5350')
p8 = draw_box(59, 50, 30, 4, "異常目標識別模型", color='#FFEBEE', edgecolor='#EF5350') 
p9 = draw_box(59, 40, 30, 4, "異常模型優化\n(提升至 50-60%)", color='#FFEBEE', edgecolor='#EF5350')
p10 = draw_box(59, 30, 30, 4, "異常行為偵測\n(持續性/突發/路徑)", color='#FFCDD2', edgecolor='#EF5350')
p11 = draw_box(59, 10, 30, 4, "異常告警與分析報告", color='#FFCDD2', edgecolor='#EF5350')

draw_arrow((p3[0]+5, p3[1]-2.5), (p7[0]-10, p7[1]+2.5)) 
draw_arrow((p7[0], p7[1]-2.5), (p8[0], p8[1]+2.5))
draw_arrow((p8[0], p8[1]-2.5), (p9[0], p9[1]+2.5))
draw_arrow((p9[0], p9[1]-2.5), (p10[0], p10[1]+2.5))
draw_arrow((p10[0], p10[1]-2.5), (p11[0], p11[1]+2.5))

plt.tight_layout()
plt.savefig('system_flowchart_large_font.png', dpi=300, bbox_inches='tight')
plt.show()