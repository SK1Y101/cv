#!/usr/bin/env python3
"""Convert details.tex to resume.json (JSON Resume schema v1.0.0)."""

import re
import json
from pathlib import Path

LATEX_CMD = re.compile(r'\\(?P<name>[a-zA-Z]+)')
COMMENT_LINE = re.compile(r'^\s*%')
FLUENCY_MAP = {'5': 'Fluent', '4': 'Advanced',
               '2': 'Novice', '1': 'Beginner', '-1': 'Native'}
ICON_TYPE = {'proj': 'hardware', 'pub': 'paper', 'code': 'software', 'talk': 'talk'}
COUNTRY_MAP = {
    'united kingdom': 'GB', 'uk': 'GB', 'england': 'GB',
    'united states': 'US', 'usa': 'US',
    'germany': 'DE', 'france': 'FR', 'japan': 'JP', 'spain': 'ES',
}


def find_brace_end(text: str, start: int) -> int:
    """Given an opening brace at start, return index of matching closing brace."""
    depth = 0
    i = start
    while i < len(text):
        if text[i] == '{':
            depth += 1
        elif text[i] == '}':
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return -1


def extract_braced(text: str, start: int) -> tuple[str | None, int]:
    """Extract the content of a braced group starting at or after `start`.
    Returns (content_or_None, next_index)."""
    i = start
    while i < len(text) and text[i] != '{':
        if text[i] == '}':
            return None, i
        i += 1
    if i >= len(text):
        return None, i
    end = find_brace_end(text, i)
    if end == -1:
        return None, len(text)
    return text[i+1:end], end + 1


def extract_command_args(text: str, start: int, count: int) -> list[str]:
    """Starting after a command name at `start`, extract `count` braced arguments."""
    args = []
    pos = start
    for _ in range(count):
        content, pos = extract_braced(text, pos)
        if content is None:
            break
        args.append(content)
    return args


def collect_commands(text: str, cmd_name: str, arg_count: int) -> list[list[str]]:
    """Find all non-commented occurrences of \\cmd_name and extract arg_count arguments."""
    results = []
    pattern = re.compile(r'\\' + cmd_name + r'(?:\s*\{)')
    for match in pattern.finditer(text):
        # Find which line this match is on
        line_start = text.rfind('\n', 0, match.start()) + 1
        line = text[line_start:text.find('\n', match.start())] if text.find('\n', match.start()) != -1 else text[line_start:]
        if COMMENT_LINE.match(line):
            continue
        args = extract_command_args(text, match.end() - 1, arg_count)
        if len(args) == arg_count:
            results.append(args)
    return results


def extract_renewcommand(text: str, cmd_name: str) -> str | None:
    """Extract the value of \\renewcommand{\\cmd_name}{...}."""
    pattern = re.compile(r'\\renewcommand\{\\' + cmd_name + r'\}')
    for m in pattern.finditer(text):
        content, _ = extract_braced(text, m.end())
        return content.strip() if content else None
    return None


def strip_latex(text: str) -> str:
    """Strip LaTeX commands, keeping readable text."""
    if not text:
        return ''
    # \href{url}{text} → text
    text = re.sub(r'\\href\{[^}]*\}\{([^}]*)\}', r'\1', text)
    # \`{text} or \`text → text (backtick accent)
    text = re.sub(r"\\`(?:'|`)?(\S)", r'\1', text)
    text = re.sub(r"\\`\{([^}]*)\}", r'\1', text)
    # \% \& \~ etc
    text = text.replace('\\%', '%').replace('\\&', '&').replace('\\~', ' ')
    # \LaTeX → LaTeX
    text = re.sub(r'\\LaTeX', 'LaTeX', text)
    # Remove remaining known commands
    text = re.sub(r'\\textbullet\s*', '', text)
    # --- →; (em dash)
    text = text.replace('---', '\u2014')
    # -- → – (en dash)
    text = text.replace('--', '\u2013')
    return text.strip()


def parse_itemize(text: str) -> list[str]:
    """Extract \\item text from within an itemize environment."""
    items = []
    for line in text.split('\n'):
        line = strip_latex(line.strip())
        if line.startswith('\\item '):
            items.append(line[6:].strip())
        elif line.startswith('\\item['):
            m = re.match(r'\\item\[([^\]]*)\]\s*(.*)', line)
            if m:
                items.append(f'{m.group(1)} {m.group(2)}'.strip())
    return items


def parse_location(address: str) -> dict:
    """Parse 'Havant, Hampshire, United Kingdom' → {'city':..., 'region':..., 'countryCode':...}"""
    parts = [p.strip() for p in address.split(',')]
    loc = {}
    if parts:
        loc['city'] = parts[0] if len(parts) >= 1 else ''
        loc['region'] = parts[-2] if len(parts) >= 3 else (parts[-1] if len(parts) == 2 else '')
        country = parts[-1].strip().lower() if parts else ''
        loc['countryCode'] = COUNTRY_MAP.get(country, country.upper()[:2].upper() if country else '')
    return loc


def split_date_range(date_str: str) -> tuple[str, str]:
    """Split '2025-09--Present' → ('2025-09', 'Present') or return (date_str, '')."""
    if '--' in date_str:
        parts = date_str.split('--', 1)
        return parts[0].strip(), parts[1].strip()
    return date_str, ''


def parse_details_tex(filepath: str) -> dict:
    with open(filepath, 'r') as f:
        content = f.read()

    resume = {}

    #  Basics
    first = extract_renewcommand(content, 'firstname') or ''
    middle = extract_renewcommand(content, 'middlename') or ''
    last = extract_renewcommand(content, 'lastname') or ''
    postnom = extract_renewcommand(content, 'postnomial') or ''
    name_parts = [first, middle, last]
    full_name = ' '.join(p for p in name_parts if p)

    # Formatted name with newline before postnomial (matches header layout)
    if postnom:
        display_name = f'{full_name}\n{postnom}'
    else:
        display_name = full_name

    basics = {
        # 'name': display_name,
        'firstname': first,
        'middlename': middle,
        'lastname': last,
        'postnomials': postnom,
    }

    photo = extract_renewcommand(content, 'profilephoto') or ''
    if photo:
        basics['image'] = f'/img/{photo}'

    email = extract_renewcommand(content, 'email') or ''
    if email:
        basics['email'] = email

    basics['phone'] = ''

    site = extract_renewcommand(content, 'website') or ''
    if site:
        basics['url'] = f'https://{site}' if not site.startswith('http') else site

    addr = extract_renewcommand(content, 'address') or ''
    if addr:
        basics['location'] = parse_location(addr)

    basics['label'] = 'Software Engineer'

    profiles = []
    gh = extract_renewcommand(content, 'githubusername') or ''
    if gh:
        profiles.append({
            'network': 'GitHub', 'username': gh,
            'url': f'https://github.com/{gh}'
        })
    li = extract_renewcommand(content, 'linkedinusername') or ''
    if li:
        profiles.append({
            'network': 'LinkedIn', 'username': li,
            'url': f'https://www.linkedin.com/in/{li}'
        })
    orcid = extract_renewcommand(content, 'orcidid') or ''
    if orcid:
        profiles.append({
            'network': 'ORCID', 'username': orcid,
            'url': f'https://orcid.org/{orcid}'
        })
    basics['profiles'] = profiles
    resume['basics'] = basics

    #  Work
    # Collect companies: {name: icon}
    companies = {}
    for args in collect_commands(content, 'addcompany', 2):
        companies[args[0]] = args[1]

    work = []
    for args in collect_commands(content, 'addposition', 6):
        company = args[0]
        position = args[1]
        team = args[2]
        start = args[3]
        end = args[4]
        details = args[5]

        entry = {
            'name': company,
            'position': position,
            'startDate': start,
        }
        if team:
            entry['team'] = team
        if end:
            entry['endDate'] = end
        if company in companies:
            entry['icon'] = companies[company]

        items = parse_itemize(details)
        if items:
            entry['summary'] = strip_latex(items[0])
            entry['highlights'] = [strip_latex(i) for i in items[1:]]

        work.append(entry)
    resume['work'] = work

    #  Education
    schools = {}
    for args in collect_commands(content, 'addeducation', 2):
        schools[args[0]] = args[1]

    education = []
    for args in collect_commands(content, 'addcourse', 6):
        institution = args[0]
        study_type = args[1]
        score = args[2]
        start = args[3]
        end = args[4]
        details = args[5]

        entry = {
            'institution': institution,
            'area': study_type,
            'studyType': study_type,
            'startDate': start,
            'endDate': end,
        }
        if score:
            entry['score'] = score
        if institution in schools:
            entry['icon'] = schools[institution]

        items = parse_itemize(details)
        if items:
            entry['courses'] = [strip_latex(i) for i in items]

        education.append(entry)
    resume['education'] = education

    #  Awards
    awards = []
    for args in collect_commands(content, 'addaward', 4):
        entry = {
            'title': args[0],
            'awarder': args[1],
            'date': args[2],
            'summary': args[3],
        }
        awards.append(entry)
    resume['awards'] = awards

    #  Memberships
    member_icons = {}
    for args in collect_commands(content, 'addmembership', 2):
        member_icons[args[0]] = args[1]

    memberships = []
    for args in collect_commands(content, 'addmembershiptitle', 7):
        institution = args[0]
        title = args[1]
        summary = args[2]
        start = args[3]
        end = args[4]
        details = args[5]
        link = args[6]

        entry = {
            'name': title,
            'institution': institution,
            'startDate': start,
        }
        if summary:
            entry['summary'] = summary
        if end:
            entry['endDate'] = end
        if details:
            entry['details'] = details
        if link:
            entry['url'] = link
        if institution in member_icons:
            entry['icon'] = member_icons[institution]
        memberships.append(entry)
    resume['memberships'] = memberships

    #  Skills
    from collections import OrderedDict
    categories = OrderedDict()
    for args in collect_commands(content, 'skill', 3):
        cat = strip_latex(args[0])
        name = strip_latex(args[1])
        if cat not in categories:
            categories[cat] = []
        categories[cat].append(name)

    # Sort keywords alphabetically within each category
    for cat in categories:
        categories[cat].sort(key=str.lower)

    category_meta = OrderedDict([
        ('Physics',         {'level': 'Master',          'icon': 'fa-solid fa-satellite'}),
        ('Languages',       {'level': 'Advanced',        'icon': 'fa-solid fa-code'}),
        ('DevOps & Cloud',  {'level': 'Software Engineer','icon': 'fa-solid fa-cloud'}),
        ('Web & Data',      {'level': 'Intermediate',    'icon': 'fa-solid fa-chart-bar'}),
    ])

    skills = []
    for cat in category_meta:
        if cat in categories:
            meta = category_meta[cat]
            entry = {'name': cat, 'level': meta['level'], 'keywords': categories[cat]}
            if meta['icon']:
                entry['icon'] = meta['icon']
            skills.append(entry)
    resume['skills'] = skills

    #  Languages
    languages = []
    for args in collect_commands(content, 'languageskill', 2):
        lang = args[0]
        fluency = FLUENCY_MAP.get(args[1], 'Beginner')
        languages.append({'language': lang, 'fluency': fluency})
    resume['languages'] = languages

    #  Interests (hobbies)
    interests = []
    for args in collect_commands(content, 'addhobby', 2):
        name = strip_latex(args[0])
        keywords = strip_latex(args[1])
        interests.append({'name': name, 'keywords': [keywords]})
    resume['interests'] = interests

    #  Publications & Projects
    publications = []
    projects = []
    for args in collect_commands(content, 'addproject', 6):
        name = args[0]
        icon = args[1]
        affiliation = args[2]
        date = args[3]
        details = args[4]
        link = args[5]

        start, end = split_date_range(date)
        entry = {
            'name': strip_latex(name),
            'description': strip_latex(details),
        }
        if start:
            entry['startDate'] = start
        if end and end.lower() != 'present':
            entry['endDate'] = end
        if link:
            entry['url'] = link
        if affiliation:
            entry['affiliation'] = affiliation

        icon_type = ICON_TYPE.get(icon, '')
        if icon_type == 'paper' or icon == 'pub':
            entry['releaseDate'] = end if end and end.lower() != 'present' else start
            publications.append(entry)
        else:
            if icon_type:
                entry['type'] = icon_type
            projects.append(entry)

    resume['publications'] = publications
    resume['projects'] = projects

    #  Schema
    resume['$schema'] = 'https://raw.githubusercontent.com/jsonresume/resume-schema/v1.0.0/schema.json'

    return resume


def main():
    import sys
    tex_path = Path(__file__).resolve().parent.parent / 'details.tex'
    if len(sys.argv) > 1:
        tex_path = Path(sys.argv[1])
    if not tex_path.exists():
        print(f'Error: {tex_path} not found', file=sys.stderr)
        sys.exit(1)

    json_path = tex_path.with_name('resume.json')

    resume = parse_details_tex(str(tex_path))
    with open(json_path, 'w') as f:
        json.dump(resume, f, indent=2, ensure_ascii=False)
    print(f'Written {json_path} ({len(json.dumps(resume))} bytes)')


if __name__ == '__main__':
    main()
