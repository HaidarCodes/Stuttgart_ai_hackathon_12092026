#!/usr/bin/env python3
"""A dependency-free local chat UI for the ERP context assistant.

Run ``python frontend.py`` and open http://127.0.0.1:8000.
"""

import argparse
import json
import os
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from openai import OpenAI

import main as assistant


PAGE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Context Ailyzer</title>
<style>
  :root { color-scheme: light; --ink:#1d1d1f; --muted:#71717a; --line:#e8e8eb; --paper:#fff; --soft:#f7f7f8; --accent:#2563eb; }
  * { box-sizing:border-box; }
  body { margin:0; background:var(--paper); color:var(--ink); font:15px/1.55 Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
  .shell { min-height:100vh; display:flex; flex-direction:column; }
  header { height:58px; padding:0 24px; display:flex; align-items:center; justify-content:space-between; border-bottom:1px solid var(--line); }
  .brand { font-weight:650; letter-spacing:-.02em; } .brand span { color:var(--muted); font-weight:450; }
  button { border:0; background:transparent; color:var(--muted); font:inherit; cursor:pointer; } .clear { border:1px solid var(--line); border-radius:8px; padding:6px 10px; color:#4b4b52; font-size:13px; } .clear:hover { color:var(--ink); border-color:#c7c7cd; }
  main { width:min(780px, calc(100% - 32px)); margin:0 auto; flex:1; padding:22px 0 156px; }
  .empty { margin:16vh auto 0; max-width:530px; text-align:center; } .empty h1 { font-size:29px; letter-spacing:-.045em; margin:0 0 8px; } .empty p { color:var(--muted); margin:0; }
  .suggestion { display:inline-block; margin-top:22px; padding:9px 13px; border:1px solid var(--line); border-radius:11px; color:#444; font-size:13px; } .suggestion:hover { border-color:#c6c6cc; }
  .message { display:grid; grid-template-columns:27px 1fr; gap:13px; margin:0 0 31px; } .avatar { width:27px; height:27px; border-radius:8px; display:grid; place-items:center; font-size:12px; font-weight:700; } .user .avatar { background:#efeff1; color:#555; } .assistant .avatar { background:#171717; color:#fff; }
  .content { min-width:0; } .content p { margin:0 0 11px; } .content p:last-child { margin-bottom:0; } .content h1,.content h2,.content h3 { letter-spacing:-.025em; margin:18px 0 8px; line-height:1.25; } .content h1 { font-size:22px; } .content h2 { font-size:18px; } .content h3 { font-size:16px; }
  .content ul,.content ol { margin:6px 0 12px; padding-left:22px; } .content code { font:12px/1.5 ui-monospace, SFMono-Regular, Consolas, monospace; background:var(--soft); padding:2px 4px; border-radius:4px; } .content pre { margin:10px 0; padding:12px; overflow:auto; background:#171717; color:#f4f4f5; border-radius:9px; font:12px/1.55 ui-monospace, SFMono-Regular, Consolas, monospace; } .content pre code { background:none; padding:0; }
  .content .table-wrap { overflow-x:auto; margin:11px 0 15px; border:1px solid var(--line); border-radius:9px; } .content table { width:100%; border-collapse:collapse; font-size:13px; } .content th,.content td { padding:8px 10px; border-bottom:1px solid var(--line); text-align:left; vertical-align:top; } .content th { background:#fafafa; font-weight:650; } .content tr:last-child td { border-bottom:0; }
  .tools { margin:13px 0 15px; display:block; } details.tool { display:block; width:100%; border:1px solid var(--line); background:#fcfcfc; border-radius:8px; margin:0 0 7px; } details.tool summary { list-style:none; padding:6px 9px; color:#60616a; font-size:12px; cursor:pointer; user-select:none; } details.tool summary::-webkit-details-marker { display:none; } details.tool summary::before { content:"›"; display:inline-block; margin-right:6px; font-size:15px; transition:transform .15s; } details.tool[open] summary::before { transform:rotate(90deg); } .tool-body { padding:0 10px 10px; } .tool-label { color:#898993; display:block; font-size:11px; margin:4px 0; } .tool-body pre { margin:0; max-height:270px; overflow:auto; white-space:pre-wrap; word-break:break-word; padding:9px; background:#f3f3f4; border-radius:6px; color:#29292e; font:11px/1.45 ui-monospace, SFMono-Regular, Consolas, monospace; }
  .typing { color:var(--muted); font-size:14px; padding-top:3px; } .dots::after { content:"..."; display:inline-block; width:16px; overflow:hidden; vertical-align:bottom; animation:dots 1.1s steps(4,end) infinite; } @keyframes dots { to { width:0; } }
  .composer-wrap { position:fixed; z-index:2; left:0; right:0; bottom:0; padding:18px max(16px, calc((100% - 780px)/2)); background:linear-gradient(transparent, #fff 28%); } .composer { display:flex; align-items:flex-end; gap:8px; border:1px solid #d9d9de; border-radius:15px; padding:8px 9px 8px 14px; box-shadow:0 7px 26px rgba(0,0,0,.07); background:#fff; } textarea { flex:1; resize:none; border:0; outline:0; max-height:160px; padding:5px 0; color:var(--ink); font:inherit; line-height:1.45; } .send { width:30px; height:30px; flex:0 0 30px; border-radius:9px; background:var(--ink); color:white; font-size:17px; line-height:1; } .send:disabled { background:#d4d4d8; cursor:not-allowed; } .hint { color:#aaa; text-align:center; font-size:11px; margin-top:7px; }
  @media (max-width:550px) { main { padding-top:16px; } header { padding:0 16px; } .composer-wrap { padding:12px 12px; } }
</style>
</head>
<body><div class="shell"><header><div class="brand">Context Ailyzer <span>· the most accurate ERP Context Chatbot</span></div><button class="clear" id="clear" title="Start a new conversation">＋ New chat</button></header><main id="chat"><section class="empty" id="empty"><h1>Ask about the records.</h1><p>The assistant can investigate the live ERP replica and show the SQL evidence it used.</p><button class="suggestion" id="suggestion">Which supplier invoices are currently stuck?</button></section></main><div class="composer-wrap"><form class="composer" id="form"><textarea id="prompt" rows="1" placeholder="Ask a follow-up or a new question…" autofocus></textarea><button class="send" id="send" type="submit" aria-label="Send">↑</button></form><div class="hint">Answers are grounded in the local ERP replica.</div></div></div>
<script>
const chat=document.querySelector('#chat'), empty=document.querySelector('#empty'), form=document.querySelector('#form'), prompt=document.querySelector('#prompt'), send=document.querySelector('#send');
let history=[];
const esc=s=>String(s??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
function inline(s){ return esc(s).replace(/`([^`]+)`/g,'<code>$1</code>').replace(/\*\*([^*]+)\*\*/g,'<strong>$1</strong>').replace(/\*([^*]+)\*/g,'<em>$1</em>'); }
function tableCells(line){return line.trim().replace(/^\||\|$/g,'').split('|').map(cell=>cell.trim());}
function tableRule(line){return tableCells(line).length>0&&tableCells(line).every(cell=>/^:?-{3,}:?$/.test(cell));}
function markdown(text){const lines=String(text||'').split('\n');let out='',list=null,code=false,codeLines=[];const close=()=>{if(list){out+=`</${list}>`;list=null;}};for(let i=0;i<lines.length;i++){const line=lines[i];if(line.startsWith('```')){if(code){out+=`<pre><code>${esc(codeLines.join('\n'))}</code></pre>`;code=false;codeLines=[];}else{close();code=true;}continue;}if(code){codeLines.push(line);continue;}if(i+1<lines.length&&line.includes('|')&&tableRule(lines[i+1])){close();const heads=tableCells(line),rows=[];i+=2;while(i<lines.length&&lines[i].includes('|')&&lines[i].trim()){rows.push(tableCells(lines[i]));i++;}i--;out+='<div class="table-wrap"><table><thead><tr>'+heads.map(cell=>`<th>${inline(cell)}</th>`).join('')+'</tr></thead><tbody>'+rows.map(row=>'<tr>'+heads.map((_,n)=>`<td>${inline(row[n]||'')}</td>`).join('')+'</tr>').join('')+'</tbody></table></div>';continue;}let m=line.match(/^(#{1,3})\s+(.*)$/);if(m){close();out+=`<h${m[1].length}>${inline(m[2])}</h${m[1].length}>`;continue;}m=line.match(/^[-*]\s+(.*)$/);if(m){if(list&&list!=='ul')close();if(!list){list='ul';out+='<ul>';}out+=`<li>${inline(m[1])}</li>`;continue;}m=line.match(/^\d+\.\s+(.*)$/);if(m){if(list&&list!=='ol')close();if(!list){list='ol';out+='<ol>';}out+=`<li>${inline(m[1])}</li>`;continue;}close();if(line.trim())out+=`<p>${inline(line)}</p>`;}close();if(code)out+=`<pre><code>${esc(codeLines.join('\n'))}</code></pre>`;return out;}
function addMessage(kind, body){ document.querySelector('#empty')?.remove(); const el=document.createElement('article');el.className=`message ${kind}`;el.innerHTML=`<div class="avatar">${kind==='user'?'Y':'AI'}</div><div class="content">${body}</div>`;chat.append(el);return el; }
function toolCard(t){const r=t.result||{},isSql=t.tool!=='write_update',meta=r.error?'error':isSql?`${r.row_count_returned??0} row${r.row_count_returned===1?'':'s'}${r.truncated?' shown (truncated)':''}`:'saved';const label=isSql?'SQL query':'Memory update',input=isSql?t.query:JSON.stringify(t.input||{},null,2);return `<details class="tool"><summary>${label} · ${meta}</summary><div class="tool-body"><span class="tool-label">${isSql?'Query':'Update'}</span><pre>${esc(input)}</pre><span class="tool-label">Response</span><pre>${esc(JSON.stringify(r,null,2))}</pre></div></details>`;}
function scroll(){ window.scrollTo({top:document.body.scrollHeight,behavior:'smooth'}); }
function size(){prompt.style.height='auto';prompt.style.height=Math.min(prompt.scrollHeight,160)+'px';}
prompt.addEventListener('input',size);prompt.addEventListener('keydown',e=>{if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();form.requestSubmit();}});
document.querySelector('#suggestion').onclick=()=>{prompt.value='Which supplier invoices are currently stuck, how much money is tied up in them, and why?';size();form.requestSubmit();};
document.querySelector('#clear').onclick=()=>{history=[];chat.innerHTML='<section class="empty" id="empty"><h1>Ask about the records.</h1><p>The assistant can investigate the live ERP replica and show the SQL evidence it used.</p></section>';prompt.focus();};
form.addEventListener('submit',async e=>{e.preventDefault();const question=prompt.value.trim();if(!question||send.disabled)return;addMessage('user',markdown(question));prompt.value='';size();send.disabled=true;const pending=addMessage('assistant','<div class="typing">Reading the question<span class="dots"></span></div>'),content=pending.querySelector('.content'),tools=document.createElement('div'),status=document.createElement('div');tools.className='tools';status.className='typing';content.replaceChildren(tools,status);const setStatus=message=>{status.innerHTML=`${esc(message)}<span class="dots"></span>`;scroll();};scroll();try{const response=await fetch('/api/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({question,history})});if(!response.ok)throw new Error((await response.json()).error||'The request failed.');const reader=response.body.getReader(),decoder=new TextDecoder();let buffer='',answer='',finished=false;for(;;){const {value,done}=await reader.read();buffer+=decoder.decode(value||new Uint8Array(),{stream:!done});let cut;while((cut=buffer.indexOf('\n\n'))>=0){const block=buffer.slice(0,cut);buffer=buffer.slice(cut+2);let event='message',data='';for(const line of block.split('\n')){if(line.startsWith('event:'))event=line.slice(6).trim();if(line.startsWith('data:'))data+=line.slice(5).trim();}if(!data)continue;const payload=JSON.parse(data);if(event==='tool'){tools.insertAdjacentHTML('beforeend',toolCard(payload));setStatus(payload.tool==='write_update'?'Saved the authoritative update · preparing response':'SQL query complete · interpreting result');}else if(event==='status'){setStatus(payload.message);}else if(event==='answer'){answer=payload.answer;status.remove();content.insertAdjacentHTML('beforeend',markdown(answer));history.push({question,answer});}else if(event==='done'){finished=true;}else if(event==='error'){throw new Error(payload.error||'The request failed.');}}if(done||finished){if(!done)await reader.cancel();break;}}}catch(err){content.innerHTML=`<p>Sorry, ${esc(err.message)}</p>`;}finally{send.disabled=false;prompt.focus();scroll();}});
</script></body></html>"""


class ChatHandler(BaseHTTPRequestHandler):
    schema = ""
    context = ""

    def log_message(self, fmt, *args):
        # Keep the terminal useful: log requests without noisy access-log lines.
        return

    def send_json(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def start_stream(self):
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.end_headers()

    def send_event(self, event, payload):
        data = json.dumps(payload, ensure_ascii=False, default=str)
        self.wfile.write(f"event: {event}\ndata: {data}\n\n".encode("utf-8"))
        self.wfile.flush()

    def do_GET(self):
        if self.path != "/":
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        body = PAGE.encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if self.path != "/api/chat":
            self.send_json(HTTPStatus.NOT_FOUND, {"error": "Not found."})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 100_000:
                raise ValueError("Request must be between 1 and 100,000 bytes.")
            payload = json.loads(self.rfile.read(length))
            question = str(payload.get("question", "")).strip()
            history = payload.get("history", [])
            if not question:
                raise ValueError("Enter a question first.")
            if len(question) > 12_000 or not isinstance(history, list):
                raise ValueError("Invalid chat request.")

            self.start_stream()
            self.send_event("status", {"message": "Planning the data investigation"})
            tools = []

            def report_tool_call(trace):
                tools.append(trace)
                self.send_event("tool", trace)
                self.send_event("status", {
                    "message": (
                        "Saved the authoritative update · preparing response"
                        if trace.get("tool") == "write_update"
                        else f"SQL query {len(tools)} complete · interpreting the result"
                    ),
                })

            con = assistant.open_read_only_db()
            try:
                answer = assistant.answer_question(
                    OpenAI(), con, self.schema, self.context, question,
                    history=history, on_tool_call=report_tool_call,
                )
            finally:
                con.close()
            self.send_event("answer", {"answer": answer})
            self.send_event("done", {})
            self.close_connection = True
        except (ValueError, json.JSONDecodeError) as exc:
            if self.wfile.closed:
                return
            self.send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
        except Exception as exc:  # Keep API errors out of the browser traceback.
            try:
                self.send_event("error", {"error": str(exc)})
            except (BrokenPipeError, ConnectionResetError):
                pass


def main():
    parser = argparse.ArgumentParser(description="Run the local ERP Context chat UI.")
    parser.add_argument("--host", default="127.0.0.1", help="Bind address (default: localhost only).")
    parser.add_argument("--port", type=int, default=8000, help="Port number (default: 8000).")
    args = parser.parse_args()

    assistant.load_env()
    if not os.environ.get("OPENAI_API_KEY"):
        raise SystemExit("OPENAI_API_KEY is not set. Add it to .env or your environment.")
    with open(assistant.SCHEMA_PATH, encoding="utf-8") as fh:
        ChatHandler.schema = fh.read()
    with open(assistant.CONTEXT_PATH, encoding="utf-8") as fh:
        ChatHandler.context = fh.read()

    server = ThreadingHTTPServer((args.host, args.port), ChatHandler)
    print(f"ERP Context is running at http://{args.host}:{args.port}")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
