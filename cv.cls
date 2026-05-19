\ProvidesClass{cv}[2023/07/17 CV class]
\NeedsTeXFormat{LaTeX2e}

\DeclareOption*{%
  \PassOptionsToClass{\CurrentOption}{article}%
}
\ProcessOptions\relax
\LoadClass{article}


\newcommand{\titleheight}{2.8cm}
\newcommand{\titlepad}{0.1cm}

% Required packages
\usepackage[yyyymmdd]{datetime}
\usepackage{enumitem}
\usepackage{fancyhdr}
\usepackage{fontawesome5}
\usepackage[T1]{fontenc}
\usepackage[headheight=12pt,footskip=10.25pt,left=0.01\paperwidth,top=\titleheight,right=0.01\paperwidth,bottom=0.016\paperheight]{geometry}
\usepackage{graphicx}
\usepackage{hyperref}
\hypersetup{colorlinks=true, linkcolor=darkblue, urlcolor=darkblue, citecolor=darkblue}
\usepackage{lmodern}
\usepackage{paracol}
\usepackage{pgffor}
\usepackage{scrextend}
\usepackage{setspace}
\usepackage{tabularx}
\usepackage{tikz}
\usepackage{worldflags}
\usepackage{xcolor}
\usepackage{xifthen}
\usepackage{xparse}
\usepackage{xstring}

% Sidebar background on every page
\usepackage{atbegshi}
\AtBeginShipout{\AtBeginShipoutUpperLeft{%
    \begin{tikzpicture}[remember picture,overlay]
        \fill[sidebarcolour] (current page.north west) rectangle ([xshift=0.2\paperwidth]current page.south west);
    \end{tikzpicture}%
}}

% Package settings

\renewcommand{\dateseparator}{-}
\renewcommand{\headrulewidth}{0pt}
\renewcommand{\footrulewidth}{0pt}
\graphicspath{{./logos/}}
\setlength{\parindent}{0pt}
\hyphenpenalty=10000
\exhyphenpenalty=10000

% Classes to print everything
\newcommand{\firstname}{First name}
\newcommand{\middlename}{}
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
\definecolor{darkblue}{HTML}{4A90D9}

\definecolor{date}{HTML}{4A90D9}

\colorlet{fillheader}{gray}
\colorlet{header}{white}
\colorlet{textcolor}{gray}
\colorlet{headercolor}{darkgrey}

% Define headers and footers

\pagestyle{fancy}
\fancyhf{}
\fancyfootoffset{0cm}
\rfoot{\footnotesize\noindent Curriculum Vitae typeset from a \TeX/\LaTeX\ file. Last updated \today}

\newcommand{\profilephoto}{}
\colorlet{entrycolour}{darkgrey}
\newcommand{\saveentrycolour}{%
    \ifcase\value{colorCounter}%
        \colorlet{entrycolour}{red}%
    \or \colorlet{entrycolour}{orange}%
    \or \colorlet{entrycolour}{green}%
    \or \colorlet{entrycolour}{aquamarine}%
    \or \colorlet{entrycolour}{blue}%
    \or \colorlet{entrycolour}{lilac}%
    \or \colorlet{entrycolour}{purple}%
    \else \colorlet{entrycolour}{lightgrey}%
    \fi
}
\newcommand{\header}[5]{%
  \begin{tikzpicture}[remember picture,overlay]
    \node [rectangle, fill=titlecolour, anchor=north, minimum width=\paperwidth, minimum height=\titleheight] (box) at (current page.north){};
    \ifx\profilephoto\empty\else
      \node [anchor=center, circle, minimum size=2.2cm, path picture={%
          \node at (path picture bounding box.center) {%
              \includegraphics[width=2.4cm,height=2.4cm]{\profilephoto}%
          };
      }] (profile) at ([xshift=0.08\paperwidth] box.west) {};
    \fi
    \node [anchor=center, align=center] (name) at (box) {%
      {\fontsize{28pt}{34pt}\color{header}%
       \bodyfont\color{highlightcolour}#1\space\thinfont\color{header}#5}\\[1mm]
      {\fontsize{18pt}{22pt}\color{header}\bodyfont #2}
    };
    \node [anchor=center] (postnomial) at ([yshift=-1.5mm] name.south) {%
      \fontsize{12pt}{16pt}\color{header}\bodyfont #3
    };
    \node [anchor=east] (pronoun) at ([yshift=-0.5mm, xshift=-0.02\paperwidth] box.east) {%
      \fontsize{12pt}{18pt}\color{header}%
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

\ExplSyntaxOff

% Define sidebar environment

\newcommand{\parbreak}{\par\vspace{2mm}}
\newcommand{\ifexists}[2]{\ifthenelse{\equal{#1}{}}{}{#2}}
\newcommand{\ifexistselse}[3]{\ifthenelse{\equal{#1}{}}{#3}{#2}}
\newcommand{\defaultexists}[2]{\ifthenelse{\equal{#1}{}}{#2}{#1}}


% Sidebar section heading (compact, for the left column)
\newcommand{\sidebarsection}[1]{
    \par\vspace{2mm}
    {\small\headingfont\color{grey}#1}
    \par\vspace{1mm}
}

% Sidebar versions of show commands

% Compact language display (human languages, like LinkedIn)
\newcommand{\showsimplelanguages}[2]{
    \ifthenelse{\getlength{#1} > 0}{
        \sidebarsection{#2}
        \foreach \n in {1,3,...,\getlength{#1}} {
            \makebox[0.35\linewidth][r]{\small\getdata[\n]{#1}}\hspace{1mm}%
            \makebox[\langflagwidth][c]{\languageflag{\getdata[\n]{#1}}}\hspace{1mm}%
            \makebox[0.35\linewidth][l]{\footnotesize\color{lightgrey}%
            \begin{switch}{\getdata[\n+1]{#1}}%
                \case{-1}{Native}%
                \case{5}{Fluent}%
                \case{4}{Advanced}%
                \case{3}{Intermediate}%
                \case{2}{Mediocre}%
                \case{1}{Beginner}%
            \end{switch}}\par
        }
    }{}
}

% Skills display (technical skills with proficiency ratings)
\newcommand{\showsidebarskills}[2]{
    \ifthenelse{\getlength{#1} > 0}{
        \sidebarsection{#2}
        \foreach \i in {-1,5,4,3,2,1} {
            \foreach \n in {1,3,...,\getlength{#1}} {
                \ifnum\getdata[\n+1]{#1}=\i\relax
                    \cvskill{\getdata[\n]{#1}}{\i}{}{S}
                \fi
            }
        }
    }{}
}

\newcommand{\showsidebarhobbies}{
    \ifthenelse{\getlength{hobbies} > 0}{
        \sidebarsection{Hobbies and Interests}
        \foreach \c in {1,3,...,\getlength{hobbies}} {
            \onehobby{\c}
        }
    }{}
}

% Compact membership rendering for sidebar
\newcommand{\showsidebarmemberships}{
    \ifthenelse{\getlength{membershiptitle} > 0}{
        \sidebarsection{Professional Memberships}
        \foreach \c in {1,7,...,\getlength{membershiptitle}} {
            {\color{darkgrey}\getdata[\c]{membershiptitle}}%
            \ifexists{\getdata[\c+1]{membershiptitle}}{\hspace{1mm}\textemdash\hspace{1mm}\getdata[\c+1]{membershiptitle}}{}%
            \par\vspace{0.5mm}
        }
    }{}
}

% Define main section wrapper
\newcommand{\mainsection}[1]{
    #1
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

\newcommand{\ratingmarker}{\faCircle}
\newcommand{\cvskill}[4]{
    % Skill name, profficiency, icon, language
    % #1~#2~#3\par
    % \ifequals{#4}{1}{Hi}
    \ifequals{#2}{-1}{\color{highlightcolour}\faIcon{heart}\space}%
    \small\ifequals{#2}{5}{\color{highlightcolour}\faIcon{heart}\space}%
    \textbf{#1}\nobreakspace
    \foreach \x in {1,...,5}{%
        \ifnum\x>1\relax\nobreak\fi
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

\newcommand{\icowidth}{2.2mm}
\newcommand{\langflagwidth}{2.8mm}

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
                \ifnum\getdata[\n+1]{#1}=\i\relax
                    \cvskill{\getdata[\n]{#1}}{\i}{\languageflag{\getdata[\n]{#1}}}{#3}
                \fi
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
\newcommand{\widedatewidth}{0.16\linewidth}

\newcommand{\parsedate}[1]{{
    \IfSubStr{#1}{--}{
        \StrBehind{#1}{--}[\CV@enddate]
        \StrBefore{#1}{--}[\CV@startdate]
        \defaultexists{\CV@enddate}{Present}\newline\CV@startdate
    }{
        \defaultexists{#1}{Ongoing}
    }
}}
\newcommand{\entrytabular}[4]{{
    \ifthenelse{\equal{\slimdates}{true}}{%
        \def\localdatewidth{\slimdatewidth}%
    }{%
        \def\localdatewidth{\widedatewidth}%
    }%
    \begin{tabularx}{\linewidth}{>{\raggedright\arraybackslash}p{\localdatewidth}>{\raggedright\arraybackslash}X}
        \vspace{-0.7em}#1
        & {\vspace{-0.7em}\color{entrycolour}#2}\ifexists{#3}{\textit{\hfill\small#3}}
        \par
        \ifexists{#4}{
            \vspace{-0.2em}
            \begin{addmargin}[0mm]{0mm}
                \setstretch{0.9}\small#4
            \end{addmargin}
        }
    \end{tabularx}
}}
\newcommand{\oneproject}[2]{
    \entrytabular
        {\parsedate{\getdata[#1+2]{#2}}}
        {\ifexistselse{\getdata[#1+5]{#2}}
            {\getdata[#1+5]{#2}\space\ifexistselse{\getdata[#1+4]{#2}}{\href{\getdata[#1+4]{#2}}{\getdata[#1]{#2}}}{\getdata[#1]{#2}}}
            {\ifexistselse{\getdata[#1+4]{#2}}{\href{\getdata[#1+4]{#2}}{\getdata[#1]{#2}}}{\getdata[#1]{#2}}}}
        {\getdata[#1+1]{#2}}
        {\getdata[#1+3]{#2}}
    \ifexistselse{\getdata[#1+3]{#2}}{\vspace{0.5em}\par}{\vspace{0.7em}\par}%
}
\newcommand{\oneitem}[2]{
    \entrytabular
        {\defaultexists{\getdata[#1+4]{#2}}{Present}\newline\getdata[#1+3]{#2}}
        {\getdata[#1+1]{#2}}
        {\getdata[#1+2]{#2}}
        {\getdata[#1+5]{#2}}
    \ifexistselse{\getdata[#1+5]{#2}}{\vspace{0.5em}\par}{\vspace{0.7em}\par}%
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
        \saveentrycolour
        \iconsection{\faIcon{#1}}{#2}%
        \vspace{0.3em}%
        \ifthenelse{\getlength{#3} < 3}{%
            \oneinstance{1}{#3}{#4}%
        }{%
            \foreach \c in {1,3,...,\getlength{#3}} {%
                \oneinstance{\c}{#3}{#4}%
            }%
        }%
        \ifthenelse{\equal{\slimdates}{true}}{
            \vspace{1.2em+0.5em}% add a little bit of extra spacing
        }{
            \vspace{0.3em+0.5em}% add a little bit of extra spacing
        }%
    }{}%
}
\newcommand{\showproject}[3]{
    % entry name
    \ifthenelse{\getlength{#3} > 0}{%
        \saveentrycolour
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
\newcommand{\showmainmemberships}[1]{
    \ifthenelse{\getlength{membershiptitle} > 0}{
        \saveentrycolour
        \iconsection{\faIcon{#1}}{Professional Memberships}
        \foreach \c in {1,8,...,\getlength{membershiptitle}} {
            \entrytabular
                {\defaultexists{\getdata[\c+4]{membershiptitle}}{Present}\newline\getdata[\c+3]{membershiptitle}}
                {\ifexistselse{\getdata[\c+6]{membershiptitle}}{\href{\getdata[\c+6]{membershiptitle}}{\getdata[\c]{membershiptitle}}}{\getdata[\c]{membershiptitle}}}
                {\getdata[\c+1]{membershiptitle}}
                {\getdata[\c+2]{membershiptitle}}
            \vspace{0.2em}\par
        }
    }{}
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
\newcommand{\addmembershiptitle}[7]{
    % \addmembershiptitle{Location}{Title}{onelinedetauks}{Start}{end}{details}{link}
    \appenddata{membershiptitle}{{#1}{#2}{#3}{#4}{#5}{#6}{#7}}
}

\newcommand{\addaward}[4]{
    % \addaward{award name}{affiliated location}{date recieved}{details}{link}
    \appenddata{awards}{{#1}{#2}{#3}{#4}{}{}}
}

\newcommand{\projicon}[1]{
    % proj: hardware, pub: paper, code: software, talk: talk
    \ifequals{#1}{proj}{\color{highlightcolour}\faIcon{microchip}}%
    \ifequals{#1}{pub}{\color{highlightcolour}\faIcon{newspaper}}%
    \ifequals{#1}{code}{\color{highlightcolour}\faIcon{keyboard}}%
    \ifequals{#1}{talk}{\color{highlightcolour}\faIcon{microphone}}%
}
\newcommand{\addproject}[6]{
    % \addproject{project name}{proj/pub}{affiliated}{completion date}{details}{link}
    \appenddata{projects}{{#1}{#3}{#4}{#5}{#6}{\projicon{#2}}}
}

\newcommand{\addhobby}[2]{
    % \addhobby{hobby name}{extra details}
    \appenddata{hobbies}{{#1}{#2}}
}
