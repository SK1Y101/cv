\ProvidesClass{cv}[2023/07/17 CV class]
\NeedsTeXFormat{LaTeX2e}

\DeclareOption*{%
  \PassOptionsToClass{\CurrentOption}{article}%
}
\ProcessOptions\relax
\LoadClass{article}


\newcommand{\titleheight}{1.75cm}
\newcommand{\titlepad}{0.1cm}

% Required packages
\usepackage{changepage}
\usepackage[yyyymmdd]{datetime}
\usepackage{enumitem}
\usepackage{fancyhdr}
\usepackage{fontawesome5}
\usepackage[T1]{fontenc}
\usepackage[left=0.01\paperwidth,top=\titleheight,right=0.01\paperwidth,bottom=0.016\paperheight,nohead,nofoot]{geometry}
\usepackage{graphicx}
\usepackage{hyperref}
\usepackage{lmodern}
\usepackage{pgffor}
% \usepackage{ragged2e}
\usepackage{scrextend}
\usepackage{setspace}
\usepackage{tabularx}
\usepackage{textpos}
\usepackage{tikz}
\usepackage{worldflags}
\usepackage{wrapfig}
\usepackage{xcolor}
\usepackage{xifthen}
\usepackage{xparse}

% Package settings

\renewcommand{\dateseparator}{-}
\renewcommand{\headrulewidth}{0pt}
\renewcommand{\footrulewidth}{0pt}
\graphicspath{{./logos/}}
\setlength{\parindent}{0pt}
% \renewcommand{\baselinestretch}{0.9}

% Classes to print everything
\newcommand{\firstname}{First name}
\newcommand{\lastname}{Last name}
\newcommand{\postnomial}{}
\newcommand{\pronoun}{}
\newcommand{\email}{}
\newcommand{\phone}{}
\newcommand{\address}{}
\newcommand{\country}{}
\newcommand{\website}{}
\newcommand{\githubusername}{}
\newcommand{\linkedinusername}{}
\newcommand{\orcidid}{}

% Define fonts

\renewcommand*\familydefault{\sfdefault}
\newcommand{\bodyfont}{\fontseries{sbc}\selectfont}
\newcommand{\thinfont}{\normalfont}
\newcommand{\headingfont}{\bfseries\fontfamily{lmss}\selectfont}

\newcommand{\italica}[1]{%
    {\color{gray}\itshape\bodyfont #1}%
}

% Define colours

\definecolor{white}{RGB}{255,255,255}

\definecolor{darkgrey}{HTML}{333333}
\definecolor{grey}{HTML}{4D4D4D}
\definecolor{lightgrey}{HTML}{999999}
\definecolor{lightergrey}{HTML}{DDDDDD}

\definecolor{blue}{HTML}{66D9EE}
\definecolor{aqua}{HTML}{7EEEEE}
\definecolor{red}{HTML}{FA2772}
\definecolor{orange}{HTML}{FE9720}
\definecolor{green}{HTML}{A7E22E}
\definecolor{lilac}{HTML}{C8A2C8}
\definecolor{purple}{HTML}{9358FE}
\definecolor{aquamarine}{HTML}{36AF90}

\definecolor{date}{HTML}{A4A4A4}

\ifdefined\@cv@print
  \colorlet{blue}{gray}
  \colorlet{red}{gray}
  \colorlet{orange}{gray}
  \colorlet{green}{gray}
  \colorlet{lilac}{gray}
  \colorlet{purple}{gray}
  \colorlet{aquamarine}{gray}
\definecolor{lightgrey}{HTML}{gray}
  \colorlet{fillheader}{white}
  \colorlet{header}{gray}
\else
  \colorlet{fillheader}{gray}
  \colorlet{header}{white}
\fi
\colorlet{textcolor}{gray}
\colorlet{headercolor}{darkgrey}

% Define headers and footers

\pagestyle{fancy}
\fancyhf{}
\fancyfootoffset{0cm}
\rfoot{\footnotesize\noindent Curriculum Vitae typeset from a \TeX/\LaTeX\ file. Last updated \today}

\newcommand{\header}[4]{%
  \begin{tikzpicture}[remember picture,overlay]
    \node [rectangle, fill=titlecolour, anchor=north, minimum width=\paperwidth, minimum height=\titleheight] (box) at (current page.north){};
    \node [anchor=center] (name) at ([yshift=2mm] box) {%
      \fontsize{40pt}{65pt}\color{header}%
      {\thinfont #1}\space{\bodyfont  #2}
    };
    \node [anchor=center] (postnomial) at ([yshift=-1mm] name.south) {%
      \fontsize{14pt}{24pt}\color{header}%
      {\bodyfont #3}
    };
    \node [anchor=left] (pronoun) at ([yshift=-2.5mm, xshift=20mm] name.east) {%
      \fontsize{14pt}{24pt}\color{header}%
      {\bodyfont #4}
    };
  \end{tikzpicture}
}

% match case syntax

\newcommand{\ifequals}[3]{\ifthenelse{\equal{#1}{#2}}{#3}{}}
\newcommand{\ifequalselse}[4]{\ifthenelse{\equal{#1}{#2}}{#3}{#4}}
\newcommand{\case}[2]{#1 #2} % Dummy, so \renewcommand has something to overwrite...
\newenvironment{switch}[1]{\renewcommand{\case}{\ifequals{#1}}}{}

% Array manipulation

\ExplSyntaxOn
\NewDocumentCommand{\storedata}{mm}
  {
   \bcp_store_data:nn { #1 } { #2 }
  }

\NewDocumentCommand{\appenddata}{mm}
 {
  \bcp_append_data:nn { #1 } { #2 }
 }

\NewExpandableDocumentCommand{\getdata}{O{1}m}
 {
  \bcp_get_data:nn { #1 } { #2 }
 }

\NewExpandableDocumentCommand{\getlength}{m}
 {
  \seq_count:c { l_bcp_data_#1_seq }
 }

\NewDocumentCommand{\removelast}{om}
 {
  \IfNoValueTF { #1 }
   {
    \bcp_remove_last:Nn \l_tmpa_tl { #2 }
   }
   {
    \bcp_remove_last:Nn #1 { #2 }
   }
 }

\cs_new_protected:Npn \bcp_store_data:nn #1 #2
 {
  % create the sequence if it doesn't exist or clear it if it exists
  \seq_clear_new:c { l_bcp_data_#1_seq }
  % append the items
  \__bcp_append_data:nn { #1 } { #2 }
 }

\cs_new_protected:Npn \bcp_append_data:nn #1 #2
 {
  % create the sequence if it doesn't exist, do nothing if it exists
  \seq_if_exist:cF { l_bcp_data_#1_seq }
   { \seq_new:c { l_bcp_data_#1_seq } }
  % append the items
  \__bcp_append_data:nn { #1 } { #2 }
 }

\cs_new_protected:Npn \__bcp_append_data:nn #1 #2
 {
  % append items one at a time
  \tl_map_inline:nn { #2 }
   {
    \seq_put_right:cn { l_bcp_data_#1_seq } { ##1 }
   }
 }

\cs_new:Npn \bcp_get_data:nn #1 #2
 {
  % retrieve the requested item
  \seq_item:cn { l_bcp_data_#2_seq } { #1 }
 }

\cs_new_protected:Nn \bcp_remove_last:Nn
 {
  \seq_pop_right:cN { l_bcp_data_#2_seq } #1
 }

\ExplSyntaxOff

% Define sidebar

\newcommand{\parbreak}{\par\vspace{2mm}}
% \newcommand{\ifexists}[2]{\ifdefempty{#1}{}{#2}}
\newcommand{\ifexists}[2]{\ifthenelse{\equal{#1}{}}{}{#2}}
\newcommand{\ifexistselse}[3]{\ifthenelse{\equal{#1}{}}{#3}{#2}}
\newcommand{\defaultexists}[2]{\ifthenelse{\equal{#1}{}}{#2}{#1}}


\newcommand{\sidebar}[1]{
    \begin{tikzpicture}[remember picture,overlay]
        \node [rectangle, fill=sidebarcolour, anchor=west, minimum width=0.2\paperwidth, minimum height=\paperheight] (bar) at ([yshift=-\titleheight] current page.west){};
        \node [anchor=north] (content) at ([yshift=-\titlepad] bar.north) {
            \begin{minipage}{0.18\paperwidth}
                \begin{flushright}
                    \thinfont\color{grey}#1
                \end{flushright}
            \end{minipage}
        };
    \end{tikzpicture}
}

% Define main section
\newcommand{\mainsection}[1]{
    \begin{adjustwidth}{0.2\paperwidth}{}{
        \vspace{-0.25cm}
        \thinfont\color{gray}#1
    }
    \end{adjustwidth}
}

%  define heading styles

% \RequirePackage{parskip}

\newcounter{colorCounter}
\def\@sectioncolor#1#2#3{%
  {%
    \color{%
      \ifcase\value{colorCounter}%
        red\or%
        orange\or%
        green\or%
        aquamarine\or%
        blue\or%
        lilac\or%
        purple\else%
        lightgrey\fi%
    } #1#2#3%
  }%
  \stepcounter{colorCounter}%
}

\renewcommand{\section}[1]{
    {\par\vspace{\parskip}
    {
        \LARGE\headingfont\color{headercolor}
        #1\parbreak
    }
    \vspace{\parskip}}
    % \vspace{-4em}
}
\newcommand{\iconsection}[2]{
  {\par\vspace{\parskip}
  {%
    \LARGE\headingfont\color{headercolor}%
    #1 \@sectioncolor #2%
  }
  \par\vspace{\parskip}}
}

\renewcommand{\subsection}[2]{
    \par\vspace{.5\parskip}
    \Large\headingfont\color{headercolor} #2\parbreak
    \vspace{.25\parskip}
}

% Skills

\newcommand{\iconlink}[3]{
    \ifexists{#1}{\ifexistselse{#2}{\href{#2#1}{#1}}{#1}~\faIcon{#3}\parbreak}
}

\newcommand{\point}{\textbullet\space}
\newcommand{\ratingmarker}{\faCircle}
\newcommand{\cvskill}[4]{
    % Skill name, profficiency, icon, language
    % #1~#2~#3\par
    % \ifequals{#4}{1}{Hi}
    \ifequals{#2}{-1}{\color{highlightcolour}\faIcon{heart}\space}%
    \small\ifequals{#2}{5}{\color{highlightcolour}\faIcon{heart}\space}%
    \textbf{#1}\space
    \foreach \x in {1,...,5}{
        \hspace{-1mm}\ifthenelse{#2=-1}{\color{skillcolour}}{\ifnumgreater{\x}{#2}{\color{lightgray}}{\color{skillcolour}}}\ratingmarker
    }
    \par\vspace{-1.5mm}
    {\footnotesize%
    \begin{switch}{#2}%
        \case{1}{Beginner}%
        \case{2}{Mediocre}%
        \case{3}{Intermediate}%
        \case{4}{Advanced}%
        \case{5}{\ifthenelse{\equal{#4}{L}}{Fluent}{Expert}}%
        \case{-1}{Native}%
    \end{switch}}
    \par\vspace{0.5mm}
}

\newcommand{\languageskill}[2]{
    \appenddata{languages}{{#1}{#2}}
}
\newcommand{\programmingskill}[2]{
    \appenddata{planguage}{{#1}{#2}}
}

\newcommand{\icowidth}{3mm}

\newcommand{\languageflag}[1]{
    \begin{switch}{#1}
        \case{German}{\worldflag[width=\icowidth]{DE}}%
        \case{English}{\worldflag[width=\icowidth]{GB}}%
        \case{Spanish}{\worldflag[width=\icowidth]{ES}}%
        \case{French}{\worldflag[width=\icowidth]{FR}}%
        \case{Italian}{\worldflag[width=\icowidth]{IT}}%
        \case{Japanese}{\worldflag[width=\icowidth]{JP}}%
        \case{Korean}{\worldflag[width=\icowidth]{KR}}%
        \case{Dutch}{\worldflag[width=\icowidth]{NL}}%
        \case{Swedish}{\worldflag[width=\icowidth]{SE}}%
    \end{switch}
}

\newcommand{\showlanguages}[3]{
    \ifthenelse{\getlength{#1} > 0}{
        \section{#2}
        \foreach \i in {-1,5,4,3,2,1} {
            \foreach \n in {1,3,...,\getlength{#1}} {
                \ifthenelse{\getdata[\n+1]{#1} = \i}{
                    \cvskill{\getdata[\n]{#1}}{\i}{\languageflag{\getdata[\n]{#1}}}{#3}
                }{}
            }
        }
    }{}
}

% Main section

\newcommand{\iconheight}{6mm}
\newcommand{\iconbox}{6.5mm}
\newcommand{\iconoffset}{.12em}

\newcommand{\marginwidth}{2mm}
\newcommand{\slimdates}{true}
\newcommand{\slimdatewidth}{0.07\linewidth}
\newcommand{\slimiconwidth}{0.001\linewidth}
\newcommand{\slimsectionwidth}{0.865\linewidth}
\newcommand{\widedatewidth}{0.16\linewidth}
\newcommand{\widesectionwidth}{0.795\linewidth}

\newcommand{\oneproject}[2]{
    % entry number, entry name
    \begin{tabularx}{\linewidth}{p{\slimdatewidth}p{\slimiconwidth}p{\slimsectionwidth}}
        \defaultexists{\getdata[#1+2]{#2}}{Ongoing} & \getdata[#1+5]{#2} & {\vspace{-3mm}\color{darkgrey}\ifexistselse{\getdata[#1+4]{#2}}{\href{\getdata[#1+4]{#2}}{\getdata[#1]{#2}}}{\getdata[#1]{#2}}}\ifexists{\getdata[#1+1]{#2}}{\textit{\hfill\small\getdata[#1+1]{#2}}}%
        \par%
        \ifexists{\getdata[#1+3]{#2}}{%
            \vspace{-0.2em}
            \begin{addmargin}[\marginwidth]{0mm}%
                \setstretch{0.9}\footnotesize\getdata[#1+3]{#2}%
            \end{addmargin}%
        }%
    \end{tabularx}%
    \ifexistselse{\getdata[#1+3]{\small#2}}{\vspace{-1.5em}\par}{\vspace{-1.4em}\par}%
}
\newcommand{\oneitem}[2]{
    % entry number, entry name
    \ifbool{\slimdates}{%
        \begin{tabularx}{\linewidth}{p{\slimdatewidth}p{\slimsectionwidth}}%
            \defaultexists{\getdata[#1+4]{#2}}{Present}\vspace{-.5mm}\newline\getdata[#1+3]{#2}%
            & {\vspace{-0.7em}\color{darkgrey}\getdata[#1+1]{#2}}\ifexists{\getdata[#1+2]{#2}}{\textit{\hfill\small\getdata[#1+2]{#2}}}%
            \par%
            \ifexists{\getdata[#1+5]{#2}}{%
                \vspace{-0.2em}%
                \begin{addmargin}[0mm]{0mm}%
                    \setstretch{0.9}\small\getdata[#1+5]{#2}%
                \end{addmargin}%
            }%
        \end{tabularx}%
        \vspace{0.5em}
    }{%
        \begin{tabularx}{\linewidth}{p{3.4em}p{0em}p{2.1em}p{\widesectionwidth}}%
            \getdata[#1+3]{#2}&%
            \hspace{-1em}\color{lightgrey}\scriptsize\faIcon{arrow-right}&%
            \hspace{-1.3em}\defaultexists{\getdata[#1+4]{#2}}{Present}&%
            {\vspace{-3mm}\color{darkgrey}\getdata[#1+1]{#2}}\ifexists{\getdata[#1+2]{#2}}{\textit{\hfill\small\getdata[#1+2]{#2}}}%
            \par%
            \ifexists{\getdata[#1+5]{#2}}{%
                \vspace{-0.2em}%
                \begin{addmargin}[0mm]{0mm}%
                    \setstretch{0.9}\small\getdata[#1+5]{#2}%
                \end{addmargin}%
            }%
        \end{tabularx}%
    }%
    \ifexistselse{\getdata[#1+5]{#2}}{\vspace{-2em}\par}{\vspace{-1.4em}\par}%
}
\newcommand{\oneinstance}[3]{
    % instance number, instance name, entry name
    \begin{addmargin}[0mm]{0mm}%
        \ifexistselse{\getdata[#1+1]{#2}}{}{\vspace{0.6em}}{\color{grey}\Large\getdata[#1]{#2}%
        \ifexistselse{\getdata[#1+1]{#2}}{\hfill%
            \raisebox{-\iconoffset}[\iconbox]{\includegraphics[height=\iconheight]{\getdata[#1+1]{#2}}}\vspace{-\iconoffset}%
        }{%
            \par%
        }}%
        \ifthenelse{\getlength{#3} < 7}{%
            \ifequals{\getdata[#1]{#2}}{\getdata[1]{#3}}{%
                \oneitem{1}{#3}%
            }%
        }{%
            \foreach \p in {1,7,...,\getlength{#3}} {%
                \ifequals{\getdata[#1]{#2}}{\getdata[\p]{#3}}{%
                    \oneitem{\p}{#3}%
                }%
            }%
        }%
    \end{addmargin}%
}
\newcommand{\showcategory}[4]{
    % icon, title, instance name, entry name
    \ifthenelse{\getlength{#3} > 0}{%
        \iconsection{\faIcon{#1}}{#2}%
        \vspace{-0.8em}%
        \ifthenelse{\getlength{#3} < 3}{%
            \oneinstance{1}{#3}{#4}%
        }{%
            \foreach \c in {1,3,...,\getlength{#3}} {%
                \oneinstance{\c}{#3}{#4}%
            }%
        }%
        \ifbool{\slimdates}{
            \vspace{1.2em+0.5em}% add a little bit of extra spacing
        }{
            \vspace{0.3em+0.5em}% add a little bit of extra spacing
        }%
    }{}%
}
\newcommand{\showproject}[3]{
    % entry name
    \ifthenelse{\getlength{#3} > 0}{%
        \iconsection{\faIcon{#1}}{#2}%
        % \vspace{-0.8em}%
        \ifthenelse{\getlength{#3} < 7}{%
            \oneproject{1}{#3}%
        }{%
            \foreach \c in {1,7,...,\getlength{#3}} {%
                \oneproject{\c}{#3}%
            }%
        }%
        \vspace{0.3em+0.5em}% add a little bit of extra spacing
    }{}%
}
\newcommand{\onehobby}[1]{
    \textbf{\getdata[#1]{hobbies}}\par
    {\color{gray}\footnotesize\getdata[#1+1]{hobbies}}\par
}
\newcommand{\showhobbies}{
    \ifthenelse{\getlength{hobbies} > 0}{
        \ifthenelse{\getlength{hobbies} < 3}{
            \onehobby{1}
        }{
            \foreach \c in {1,3,...,\getlength{hobbies}} {
                \onehobby{\c}
            }
        }
    }{}
}

\newcommand{\addcompany}[2]{
    \appenddata{jobcompanies}{{#1}{#2}}
}
\newcommand{\addposition}[6]{
    % \addposition{Company}{Role}{Start}{end}{details}
    \appenddata{jobpositions}{{#1}{#2}{#3}{#4}{#5}{#6}}
}

\newcommand{\addeducation}[2]{
    \appenddata{educationschools}{{#1}{#2}}
}
\newcommand{\addcourse}[6]{
    % \addcourse{School}{grade}{course}{Start}{end}{details}
    \appenddata{educationcourses}{{#1}{#2}{#3}{#4}{#5}{#6}}
}

\newcommand{\addmembership}[2]{
    \appenddata{membership}{{#1}{#2}}
}
\newcommand{\addmembershiptitle}[6]{
    % \addmembershiptitle{Location}{Title}{onelinedetauks}{Start}{end}{details}
    \appenddata{membershiptitle}{{#1}{#2}{#3}{#4}{#5}{#6}}
}

\newcommand{\addaward}[4]{
    % \addaward{award name}{affiliated location}{date recieved}{details}{link}
    \appenddata{awards}{{#1}{#2}{#3}{#4}{}{}}
}

\newcommand{\projicon}[1]{
    % proj: hardware, pub: paper, code: software, talk: talk
    \ifexistselse{#1}{}{\faIcon{paste}}
    \ifequals{#1}{proj}{\faIcon{microchip}}
    \ifequals{#1}{pub}{\faIcon{newspaper}}
    \ifequals{#1}{code}{\faIcon{keyboard}}
    \ifequals{#1}{talk}{\faIcon{microphone}}
}
\newcommand{\addproject}[6]{
    % \addproject{project name}{proj/pub}{affiliated}{completion date}{details}{link}
    \appenddata{projects}{{#1}{#3}{#4}{#5}{#6}{\projicon{#2}}}
}

\newcommand{\addhobby}[2]{
    % \addhobby{hobby name}{extra details}
    \appenddata{hobbies}{{#1}{#2}}
}