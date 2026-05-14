---
name: latex
description: Write and compile LaTeX documents with xelatex/lualatex/pdflatex. Use when the user asks to create PDFs, write papers/reports/resumes, typeset math, or produce any LaTeX-based document output.
---

# LaTeX

## 环境

TeX Live (2023/Debian)，支持 xelatex、pdflatex、lualatex。

## 编译命令

```bash
# 中文文档（默认用 xelatex，需要编译两次确保目录/引用）
xelatex -shell-escape file.tex
xelatex -shell-escape file.tex

# 英文文档
pdflatex file.tex

# 带参考文献
xelatex file.tex
bibtex file
xelatex file.tex
xelatex file.tex

# 清理辅助文件
rm -f *.aux *.log *.out *.toc *.bbl *.blg *.nav *.snm
```

## 通用模板

### 中文文章（xelatex）

```latex
\documentclass[12pt,a4paper]{article}
\usepackage[UTF8]{ctex}
\usepackage{geometry,amsmath,amssymb,graphicx,hyperref}
\geometry{left=2.5cm,right=2.5cm,top=2.5cm,bottom=2.5cm}

\title{标题}
\author{作者}
\date{\today}

\begin{document}
\maketitle
\tableofcontents
\newpage

\section{引言}
内容。

\end{document}
```

### 英文文章（pdflatex）

```latex
\documentclass[11pt,a4paper]{article}
\usepackage{geometry,amsmath,amssymb,graphicx,hyperref}
\geometry{margin=1in}

\title{Title}
\author{Author}
\date{\today}

\begin{document}
\maketitle
\tableofcontents
\newpage

\section{Introduction}
Content.

\end{document}
```

### Beamer 幻灯片

```latex
\documentclass{beamer}
\usepackage[UTF8]{ctex}
\usetheme{Madrid}

\title{标题}
\author{作者}
\date{\today}

\begin{document}
\frame{\titlepage}

\begin{frame}{目录}
\tableofcontents
\end{frame}

\section{第一节}

\begin{frame}{标题}
\begin{itemize}
    \item 第一点
    \item 第二点
\end{itemize}
\end{frame}
\end{document}
```

### 简历

```latex
\documentclass[10pt]{article}
\usepackage{geometry,enumitem,hyperref,xcolor}
\geometry{margin=0.8in}

\pagestyle{empty}

\begin{document}
\vspace*{-1cm}
{\LARGE\bfseries 姓名} \hfill 邮箱@example.com \\
电话: 123-4567-890 \hfill GitHub: username

\section*{教育经历}
\textbf{学校} \hfill 年份--年份 \\
学位 \hfill 专业

\section*{技能}
\begin{itemize}[nosep,left=0pt]
    \item Python, C++, Java
    \item LaTeX, Git, Linux
\end{itemize}
\end{document}
```

## 常用中文字体

```latex
% 设置中文字体（根据系统可用字体）
\setCJKmainfont{Noto Serif CJK SC}
\setCJKsansfont{Noto Sans CJK SC}
\setCJKmonofont{Noto Sans Mono CJK SC}
```

## 常用宏包速查

| 宏包 | 用途 | 示例 |
|------|------|------|
| `ctex` | 中文支持 | `\documentclass{ctexart}` |
| `geometry` | 页面边距 | `\geometry{margin=1in}` |
| `amsmath` | 数学公式 | `\begin{equation}...\end{equation}` |
| `graphicx` | 图片插入 | `\includegraphics{fig.png}` |
| `hyperref` | 超链接 | `\href{url}{text}` |
| `booktabs` | 三线表 | `\toprule \midrule \bottomrule` |
| `listings` | 代码排版 | `\begin{lstlisting}` |
| `algorithm2e` | 伪代码 | `\begin{algorithm}` |
| `tikz` | 矢量绘图 | `\draw (0,0) -- (1,1);` |
| `biblatex` | 参考文献 | `\addbibresource{ref.bib}` |
| `enumitem` | 列表定制 | `\begin{itemize}[nosep]` |

## MATLAB 生成匹配 PNG/PDF 的图表

MATLAB `print` 输出的 PNG 和 PDF 默认不同（PNG 按图实际尺寸，PDF 缩放至 letter），
导致比例、字体大小不一致。统一方法：

```matlab
% 绘图后，统一渲染器 + 强制 PDF 与图尺寸一致
set(fig, "Renderer", "opengl");          % 统一渲染器
set(fig, "PaperUnits", "points");        % 单位设为 point
set(fig, "PaperPosition", [0 0 W H]);    % 与 figure Position 的 WH 一致
set(fig, "PaperSize", [W H]);            % 页面大小 = 图大小

print(fig, "output.png", "-dpng", "-r200");
print(fig, "output.pdf", "-dpdf");
fprintf("Saved!\n");
```

**关键点**：
- `PaperSize` 必须设为图的 W×H，否则 PDF 默认 letter（612×792pt）
- `PaperPosition` 从 (0,0) 开始铺满
- 渲染器统一为 `opengl`（软件 OpenGL 也行，PDF/PNG 一致即可）
- `-r200` 控制 PNG 分辨率，PDF 不受影响（矢量）
