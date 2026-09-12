#!/usr/bin/env python3
"""Answer ERP questions with an LLM that can investigate the SQLite database.

Usage:
    python main.py
    python main.py "which suppliers are blocked?"

The model may call ``run_sql`` repeatedly before it returns its final answer.
"""

import json
import os
import sqlite3
import sys
import time

try:
    from openai import OpenAI, BadRequestError
except ImportError:
    sys.exit("Missing dependency. Run: python -m pip install -r requirements.txt")


HERE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(HERE, "data", "erp_legacy.db")
# Full DDL for every populated table (1,096 structurally-empty tables removed,
# see build_filtered_schema.py / context.md section 7), not just the 14-table
# extract - the extract alone cannot answer questions outside schema.sql and
# fails the "does it work on all 1,274 tables" requirement.
SCHEMA_PATH = os.path.join(HERE, "data", "schema_filtered_full.sql")
CONTEXT_PATH = os.path.join(HERE, "context.md")
MAX_ROWS = 100
MAX_CELL_CHARS = 2000  # protect against a single huge cell (e.g. group_concat) blowing up the context
SQL_TIMEOUT_SECONDS = float(os.environ.get("SQL_TIMEOUT_SECONDS", "10"))

DEFAULT_QUESTION = "How many supplier invoices are currently stuck in verification?"

SYSTEM_PROMPT = """You are the system of context sitting on top of a 20-year-old
purchase-to-pay ERP replica (SQLite). The database is a perfect system of
records: it knows exactly what happened. It knows nothing about what any of
it means. Your job is to take a question phrased in business language,
understand what it means in terms of this database, answer it correctly, and
show your work - so that a finance department could actually verify you.

MISSION AND STANDARD OF A GOOD ANSWER
A bare number is not a good answer. For "which invoices are stuck" the
business wants to know which invoices, from which vendors, how much money,
how long they have been sitting there, and why - and they want to be able to
check it. Whenever a question is about a set of documents (invoices, orders),
identify the documents and key facts about them (vendor, amount, status,
age), not just a count or sum, unless the question is explicitly a plain
count/sum. State the rule you applied in business terms, then the SQL-backed
result, then the source(s) the rule came from. An answer nobody can trace
back to underlying records or to where the rule came from is worth very
little here - provenance is not a nice-to-have, it is the product.

METHODOLOGY
You have a read-only SQL tool. Use it whenever a number, a record, or a
distribution is needed - never guess or estimate a query result. Investigate
before you compute: check what values a status/flag field actually takes,
check for nulls/blanks, check row counts, before trusting an assumption about
it. Do not just pick whichever context source sounds most authoritative and
do not assume a majority of sources agreeing makes something true - several
documents can share the same outdated original. Instead, turn a documented
claim into a testable prediction and check it against the data (e.g. "this
status should mean approved, so these documents should have a matching
payment record - do they?"). The context pack below already ran this process
once and records both what the documentation claims and what the database
actually confirmed, with a source tag for each fact - reuse those conclusions
directly instead of re-deriving them, but re-verify with SQL whenever a
question depends on a claim the context pack flags as unresolved, unverified,
or only partially checked, or when something about the live data looks
inconsistent with it.

Never rely on a fixed lookup table of question-to-answer mappings. Questions
you are asked may be phrased like, but are not identical to, any example
you've seen - rederive the answer from the schema, the context pack's
semantics, and fresh SQL every time.

THE ANALYSIS DATE
The database extract was taken on 2026-03-01 and contains nothing dated
after that. When a question says "currently", "now", "still", or "as of
today", it means 2026-03-01 - use that literal date for any age/duration
calculation relative to "now", not SQLite's real system clock
(date('now')/CURRENT_DATE would read the wrong date). Also note: every
date-like column in this database is stored as TEXT in YYYYMMDD format
(e.g. '20250120'), not ISO YYYY-MM-DD. String equality/ordering on
YYYYMMDD works correctly as-is, but SQLite's date()/julianday()/strftime()
functions require YYYY-MM-DD and will silently return NULL on a raw
YYYYMMDD string - reformat first (e.g. via substr concatenation) before
doing date arithmetic.

KEY TRAPS TO WATCH FOR (all detailed with sources in the context pack)
- Status codes are not what an outdated data catalogue claims; the
  authoritative source is the transition log, not a static lookup table.
- "Block" is overloaded: a vendor block, a verification block, and a payment
  block are three different fields for three different things - do not
  conflate them.
- Deleted/cancelled line items are flagged, not removed, and must be
  filtered out of value calculations; a "deleted" flag on a material master
  record is a different, unrelated concept from a deleted order line.
- Price fields may be per price unit, not per piece - dividing by the wrong
  unit inflates results by orders of magnitude.
- Cross-currency totals require conversion at the correct date using the
  exchange-rate table; summing document-currency amounts directly is
  meaningless.
- A join across the core entities may silently drop rows with no matching
  counterpart (a migration left some references dangling) - use LEFT JOINs
  and account for orphans rather than losing them silently.
- A vendor or material name is not a unique key; resolve business-entity
  references to their numeric ID before answering anything about them.

TABLE TRUST AND SCALE
The schema below covers every populated table in the database (structurally
empty tables have already been removed), not just the 14-table core extract -
the same reasoning must generalise to the full database, not just the
hand-picked tables. Most of the non-core tables are unrelated noise:
plausible-looking table and column names whose key values do not actually
intersect the core P2P entities (vendors, materials, purchase orders,
invoices). Before joining an unfamiliar table to the core tables, verify with
a query that its key-like columns (e.g. anything resembling LIFNR, EBELN,
MATNR, BELNR) actually contain values that exist in the corresponding core
table - do not assume a shared column name implies a shared entity. Likewise,
prefer the live core tables over lookalike backup, staging, shadow, or
archive tables unless the question explicitly concerns historic/archived
data; the context pack lists which lookalikes are known-genuine historical
data versus known-stale copies, and even that must be checked per table
rather than assumed from the name.

OUTPUT
Answer only after at least one run_sql call has actually been executed for
this question, unless the question is purely definitional (e.g. "what does
status 60 mean") and genuinely needs no data lookup - if you try to finalize
without ever having queried the database, you will be asked to verify first.
Format the final answer as clean Markdown. State the business rule you used in plain language,
give the result (with the underlying documents/vendors/amounts when the
question is about a set of records), and cite the relevant context-pack
source tag(s) (e.g. [glossary], [ticket INC0xxxxx], [email Thread N], [DB])
alongside a compact description of the SQL evidence you gathered. Never
expose internal tool-call syntax to the user.

Relevant schema:
{schema}

Context pack:
{context}
"""

TOOLS = [{
    "type": "function",
    "function": {
        "name": "run_sql",
        "description": (
            "Run one read-only SQLite query against the live ERP replica. "
            "Use this to inspect or validate data before answering. Results are capped."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "A single read-only SQLite SELECT, WITH, EXPLAIN, or PRAGMA query.",
                }
            },
            "required": ["query"],
            "additionalProperties": False,
        },
    },
}]


def load_env():
    """Minimal .env loader so no additional package is needed."""
    path = os.path.join(HERE, ".env")
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def open_read_only_db():
    """Open the replica defensively: this program must never mutate ERP data."""
    db_uri = "file:" + DB_PATH.replace("\\", "/") + "?mode=ro"
    con = sqlite3.connect(db_uri, uri=True)
    con.execute("PRAGMA query_only = ON")
    return con


def _bound_cell(value):
    """Truncate an individual result cell so one huge value can't blow up the
    model's context (e.g. a stray group_concat() or a giant text column)."""
    if isinstance(value, str) and len(value) > MAX_CELL_CHARS:
        return value[:MAX_CELL_CHARS] + f"... [truncated, {len(value)} chars total]"
    return value


def run_sql(con, query):
    """Execute one read-only statement and serialize a bounded, model-friendly result."""
    if query is not None and not isinstance(query, str):
        return {"error": f"'query' must be a string, got {type(query).__name__}."}
    query = (query or "").strip()
    if not query:
        return {"error": "No SQL query was provided."}

    # sqlite3.execute rejects multiple statements. This early check makes the
    # restriction clear to the model and avoids accidental write attempts.
    normalized = query.rstrip().rstrip(";").lstrip().upper()
    if not normalized.startswith(("SELECT", "WITH", "EXPLAIN", "PRAGMA")):
        return {"error": "Only one read-only SELECT, WITH, EXPLAIN, or PRAGMA statement is allowed."}

    # Abort runaway queries instead of hanging the whole session on one bad
    # cross join. set_progress_handler fires periodically during execution;
    # returning truthy aborts the statement with sqlite3.OperationalError.
    deadline = time.monotonic() + SQL_TIMEOUT_SECONDS
    con.set_progress_handler(lambda: time.monotonic() > deadline, 1000)
    try:
        cursor = con.execute(query)
        columns = [column[0] for column in cursor.description] if cursor.description else []
        rows = cursor.fetchmany(MAX_ROWS + 1)
        truncated = len(rows) > MAX_ROWS
        if truncated:
            rows = rows[:MAX_ROWS]
        return {
            "columns": columns,
            "rows": [[_bound_cell(value) for value in row] for row in rows],
            "row_count_returned": len(rows),
            "truncated": truncated,
        }
    except sqlite3.OperationalError as exc:
        if "interrupted" in str(exc).lower():
            return {"error": f"Query aborted after {SQL_TIMEOUT_SECONDS:.0f}s (too slow). Add filters/LIMIT or aggregate in SQL instead of scanning raw rows."}
        return {"error": f"SQLite error: {exc}"}
    except sqlite3.Error as exc:
        return {"error": f"SQLite error: {exc}"}
    finally:
        con.set_progress_handler(None, 0)


def call_model(client, model, messages, extra_kwargs, tool_choice="auto"):
    """One Chat Completions call, with request kwargs the caller can adapt.

    extra_kwargs may contain "_omit_temperature" (internal flag, stripped
    before the call) plus any additional keyword to merge into the request,
    e.g. {"reasoning_effort": "none"}.
    """
    extra_kwargs = dict(extra_kwargs)
    omit_temperature = extra_kwargs.pop("_omit_temperature", False)
    kwargs = {
        "model": model,
        "messages": messages,
        "tools": TOOLS,
        "tool_choice": tool_choice,
    }
    if not omit_temperature:
        kwargs["temperature"] = 0
    kwargs.update(extra_kwargs)
    return client.chat.completions.create(**kwargs)


def answer_question(client, con, schema, context, question, history=None, on_tool_call=None):
    """Run the Chat Completions tool loop until the model supplies an answer.

    ``on_tool_call`` receives a dictionary containing the query and its
    serialized result. The CLI prints that trace; the web frontend displays it
    as expandable evidence cards.
    """
    max_tool_rounds = int(os.environ.get("MAX_TOOL_ROUNDS", "10"))
    model = os.environ.get("OPENAI_MODEL", "gpt-4o")
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT.format(schema=schema, context=context)},
    ]
    for turn in (history or [])[-8:]:
        if isinstance(turn, dict) and turn.get("question") and turn.get("answer"):
            messages.extend([
                {"role": "user", "content": str(turn["question"])},
                {"role": "assistant", "content": str(turn["answer"])},
            ])
    messages.append({"role": "user", "content": question})

    # Some reasoning models (e.g. gpt-5.x) reject function tools on the Chat
    # Completions endpoint unless reasoning_effort is explicitly turned off,
    # and/or reject a fixed temperature. Discover that adaptively instead of
    # hardcoding it per model name, and remember the fix for the rest of this
    # run once it's been established.
    extra_kwargs = {}

    any_sql_executed = False  # at least one run_sql call actually made, success or not
    nudged_for_evidence = False  # only nudge once, to avoid looping forever

    def call_with_fallback(tool_choice="auto"):
        try:
            return call_model(client, model, messages, extra_kwargs, tool_choice=tool_choice)
        except BadRequestError as exc:
            msg = str(exc)
            if "reasoning_effort" in msg and extra_kwargs.get("reasoning_effort") != "none":
                extra_kwargs["reasoning_effort"] = "none"
            elif "temperature" in msg and not extra_kwargs.get("_omit_temperature"):
                extra_kwargs["_omit_temperature"] = True
            else:
                raise
            return call_model(client, model, messages, extra_kwargs, tool_choice=tool_choice)

    for _ in range(max_tool_rounds):
        response = call_with_fallback()
        message = response.choices[0].message
        messages.append(message)

        if not message.tool_calls:
            if any_sql_executed or nudged_for_evidence:
                return message.content or "I could not produce an answer."
            # The model tried to finalize without ever consulting the
            # database. Nudge it once instead of silently accepting an
            # unverified answer (see SYSTEM_PROMPT's OUTPUT section).
            nudged_for_evidence = True
            messages.append({
                "role": "user",
                "content": (
                    "Before finalizing, verify this with at least one run_sql "
                    "call against the live database (unless the question is "
                    "purely definitional), then answer again."
                ),
            })
            continue

        for tool_call in message.tool_calls:
            raw_query = "<invalid arguments>"
            try:
                arguments = json.loads(tool_call.function.arguments)
                if not isinstance(arguments, dict):
                    raise TypeError(f"tool arguments must be a JSON object, got {type(arguments).__name__}")
                raw_query = arguments.get("query")
                result = run_sql(con, raw_query)
            except (json.JSONDecodeError, TypeError) as exc:
                result = {"error": f"Malformed tool call, ignored: {exc}"}
            any_sql_executed = True

            trace = {
                "query": raw_query if isinstance(raw_query, str) else "<invalid arguments>",
                "result": result,
            }
            if on_tool_call:
                on_tool_call(trace)
            else:
                print("\nSQL TOOL CALL\n-------------")
                print(trace["query"])
                print("RESULT", json.dumps(result, ensure_ascii=False, default=str))
            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": json.dumps(result, ensure_ascii=False, default=str),
            })

    # Exhausted the investigation budget but the model was still calling
    # tools. Force one last text-only answer from whatever evidence has
    # already been gathered, instead of silently giving up.
    messages.append({
        "role": "user",
        "content": (
            f"You have reached the limit of {max_tool_rounds} SQL investigation "
            "rounds. Answer now using only the evidence already gathered above, "
            "and say explicitly if part of the question could not be fully "
            "verified in that time."
        ),
    })
    try:
        response = call_with_fallback(tool_choice="none")
        content = response.choices[0].message.content
        if content:
            return content
    except Exception:
        pass

    return (
        f"I reached the safety limit of {max_tool_rounds} SQL investigation rounds "
        "and could not produce a final answer even after asking for one. "
        "Increase MAX_TOOL_ROUNDS and retry."
    )


def main():
    load_env()
    if not os.environ.get("OPENAI_API_KEY"):
        sys.exit("OPENAI_API_KEY is not set. Add it to .env or your environment.")

    question = " ".join(sys.argv[1:]) or DEFAULT_QUESTION
    with open(SCHEMA_PATH, encoding="utf-8") as fh:
        schema = fh.read()
    with open(CONTEXT_PATH, encoding="utf-8") as fh:
        context = fh.read()

    print("=" * 70)
    print("QUESTION:", question)
    print("=" * 70)

    client = OpenAI()
    con = open_read_only_db()
    try:
        answer = answer_question(client, con, schema, context, question)
    finally:
        con.close()

    print("\nFINAL ANSWER\n------------")
    print(answer)


if __name__ == "__main__":
    main()
