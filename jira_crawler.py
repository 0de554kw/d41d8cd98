#!/usr/bin/env python
"""
-----------------------------------------------------------------------------------------------------------------------
Copyright <2022> <x0de554kw1n>

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated
documentation files (the "Software"), to deal in the Software without restriction, including without limitation
the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software,
and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or substantial portions
 of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE
WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR
COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR
OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

-----------------------------------------------------------------------------------------------------------------------
"""

# Standard packages
import argparse
from calendar import monthrange
import datetime
import json
import os
import re
import requests
import sys
import tempfile
import numpy as np
import urllib3


def process_args():
    parser = argparse.ArgumentParser("python jira_crawler.py", formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("--html",
                        type=str,
                        dest="html_file",
                        help=f"Result HTML file (Default: out.html)",
                        default='out.html')
    parser.add_argument("--config_path",
                        type=argparse.FileType("r"),
                        dest="config_path",
                        required=True,
                        help="Path to credentials JSON file.")
    parser.add_argument("--assignee",
                        type=str,
                        dest="assignee",
                        help="Issue here assignee ID to get worklog for specified worker")
    parser.add_argument("--last_year",
                        type=int,
                        dest="year",
                        help="Last year in report (Default: current year)",
                        default=datetime.datetime.now().year)
    parser.add_argument("--last_month",
                        type=int,
                        dest="month",
                        help="Last month in report (1-12) (Default: current month)",
                        default=datetime.datetime.now().month)
    parser.add_argument("--depth",
                        type=int,
                        dest="depth",
                        help=f"Months in report (Default: 1)",
                        default=1)
    parser.add_argument("-JQL",
                        dest="jql",
                        help="JIRA queri language line",
                        action='store_true')
    args = parser.parse_args()
    return args


class JCrawler:

    RAW_DATA_PATH = "raw_data"

    def __init__(self, args):
        self.project = ""
        self.jira_url = ""
        self.assignee = ""
        self.user_name = ""
        self.pwd = ""
        self.jql = ""
        self.responces = {}
        self.tmp_folders()
        self.max_results = 1000
        self.args = args
        self.process(self.args)

    def tmp_folders(self):
        os.makedirs(self.RAW_DATA_PATH, exist_ok=True)

    def process(self, args: argparse) -> None:
        config_json = json.load(args.config_path)
        self.user_name = config_json.get("username")
        self.pwd = config_json.get("password")
        self.project = config_json.get("project")
        if not self.project:
            raise RuntimeError("[FATAL] No project is sourced for crawl")
        self.jira_url = config_json.get("jira_url")
        if not self.jira_url:
            raise RuntimeError("[FATAL] No JIRA URL is sourced for crawl")
        if args.assignee:
            self.assignee = args.assignee
        if args.jql:
            self.jql = args.jql
        elif config_json.get("jql"):
            self.jql = config_json.get("jql")
        else:
            self.jql = '+order+by+id'
        self.max_results = int(config_json.get("max_results"))
        self.get_searches()
        self.parse_search()
        self.generate_html(args)

    def get_searches(self) -> None:

        def inner(p: int):
            uri = f"/rest/api/2/search?jql=project={self.project}"
            if self.assignee:
                uri += f"+AND+worklogAuthor={self.assignee}"
            uri += f"{self.jql}&fields=key,worklog&maxResults={self.max_results}&startAt={self.max_results * p}"
            url = self.jira_url + uri
            print(f"Get url response {url}")
            response = requests.get(url, auth=(self.user_name, self.pwd), verify=False)
            self.responces[p] = response.text

        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        inner(0)
        loaded_json = json.loads(self.responces.get(0))
        total = loaded_json.get("total")
        if total:
            pages = (total - 1) // 1000
            sss = 's' if total > 1 else ''
            print(f"Found {total} issue{sss}. Need to download {pages} page{sss} more.")
            for page in range(1, pages + 1):
                print(f"Loading page {page} out of {pages}")
                inner(page)
        else:
            raise Exception(f"{loaded_json.get('errorMessages')}")

    def parse_search(self) -> None:
        def inner(dict_: dict) -> str:
            out = ""
            issues = dict_["issues"]
            for issue in issues:
                out += f'{issue["key"]}\n'
                out += f'{issue["fields"]["worklog"]["total"]}\n'
                for i in range(min(issue["fields"]["worklog"]["total"], issue["fields"]["worklog"]["maxResults"])):
                    work = issue["fields"]["worklog"]["worklogs"][i]
                    try:
                        out = f'{out}{work["author"]["displayName"]} {work["started"][:10]} {work["timeSpent"]}\n'
                    except KeyError as key:
                        print(f"[DEBUG in parse_search_data] line {work} has got an KeyError exception {key}")
                        out = f'{out}{work["author"]["name"]} {work["started"][:10]} {work["timeSpent"]}\n'
            return out

        result = ""
        for p in self.responces.keys():
            result += inner(json.loads(self.responces.get(p)))
        txt_path = f"{self.RAW_DATA_PATH}/data.txt"
        with open(txt_path, "w", encoding="utf-8") as f:
            f.write(result)

    def load_table(self) -> dict:

        def inner(line_: str) -> float:
            line_ = line_.strip()
            g = re.match(r"(\d+)(\w)", line_)
            time_, factor = g.groups()
            factors = {
                "m": 0.01666,
                "h": 1.0,
                "d": 8.0,
                "w": 40.0,
            }
            return float(time_) * factors.get(factor)

        fn = f"{self.RAW_DATA_PATH}/data.txt"
        with open(fn) as chunk:
            lines = chunk.readlines()
        current_task = ""
        table = {}
        for line in lines:
            long_line = re.match(r"(\w{1,10}, \w{1,10}X)\s(\d{4}-\d{2}-\d{2})\s(\d{1,2}\w\n$)", line)
            task_line = re.match(r"^\w{3,5}-\d{1,10}\n$", line)
            if long_line:
                name = long_line.group(1)
                date = long_line.group(2)
                time = long_line.group(3)
                time = inner(time)
                if name not in table:
                    table[name] = {}
                if date not in table[name]:
                    table[name][date] = []
                table[name][date].append({'task': current_task, 'time': time})
            if task_line:
                current_task = line.strip("\n")
        return table

    def month_table(self, month, year, table) -> None:
        def inner(blocks: list, id_: str, date_):
            temp = 0
            html = f'{date_}<table>'
            for block in blocks:
                b_time = block['time']
                temp = temp + b_time
                url = f"{self.jira_url}/browse/{block['task']}"
                html += f'<tr><td><a href=\\\'{url}\\\' target=\\\'blank\\\'>{url}</td><td>{b_time:0.3g}h</td></tr>'
            sresult_ = '<div style="cursor:pointer;" onclick="document.getElementById'
            sresult_ += f'(\'{id_}\').innerHTML=\'{html}\';">{temp:0.3g}</div>'
            return temp, sresult_

        title = datetime.date(1900, month, 1).strftime('%B')
        days = monthrange(year, month)[1]
        output_id = title + str(year)

        first_day = datetime.date(year, month, 1)
        last_day = datetime.date(year, month, days)
        work_days = np.busday_count(first_day, last_day)
        work_hours = int(work_days) * 8

        print(f"<h1>{title} {year}</h1><table border=1><tr><td></td>")

        for i in range(1, days + 1):
            date = f"{year:04d}-{month:02d}-{i:02d}"
            print(f"<td width=30px align=center>{date}</td>")
        print("<td align=center>&sum;</td></td>")
        print("<td align=center>Debt</td></td>")

        grand_total = 0
        for line in table:
            print(f"<tr><td>{line}</td>")
            total = 0
            for i in range(1, days + 1):
                print("<td align=center>", end='')
                date = f"{year:04d}-{month:02d}-{i:02d}"
                if date in table[line]:
                    time, sresult = inner(table[line][date], output_id, date)
                    print(sresult, end='')
                    total = int(total + time)
                print("</td>", end='')
            print(f"<td align=center><b>{total:0.4g}</b></td>")
            print(f"<td align=center><b>{-(total - work_hours):0.4g}</b></td></tr>")
            grand_total += total

        print(f"<tr><td colspan='{days + 2}'><b>Grand Total: {grand_total:0.5g}</b></td></tr>")
        print(f"<tr><td colspan='{days + 2}' id='{output_id}'>Click by cells for details</td></tr></table>")

    def generate_html(self, args: argparse) -> None:
        table = self.load_table()
        orig_stdout = sys.stdout
        with open(args.html_file, 'w') as output_file:
            sys.stdout = output_file
            print("<html><head><title>Summary by workers</title><style type='text/css'></style></head><body>")
            for _ in range(args.depth):
                self.month_table(args.month, args.year, table)
                args.month = args.month - 1
                if args.month <= 0:
                    args.month = 12
                    args.year = args.year - 1
            print("</html>")
            sys.stdout = orig_stdout


def main() -> None:
    args = process_args()
    JCrawler(args)


if __name__ == "__main__":
    main()
