#!/usr/bin/env python

from flask import Flask,render_template,send_from_directory
import re


def parse_markdown(md):
    f = lambda m: (m.split(" --> ",1)[0].strip(),) + (
        (lambda l: (r.groups() if (r := re.search(r"\[(.*?)\]\((.*?)\)", l)) else (l.strip(), None)))(m.split(" --> ",1)[1])
        if " --> " in m else (None, None)
    )
    return [f(m) for m in re.findall(r"- \[[x ]\] (.*)", md)]

app = Flask(__name__)

@app.route("/")
def main():
    with open("README.md","r") as file:
        markdown=file.read()
        wishes=parse_markdown(markdown)
        return render_template("index.html",wishes=wishes)

@app.route('/style.css')
def style():
    return send_from_directory('static', 'style.css')

if __name__=="__main__":
    app.run("0.0.0.0",5000)
