from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import hashlib
import json
import sqlite3
import time
import os


app = FastAPI()


DB = "agent.db"


# -------------------------
# Database
# -------------------------

def init_db():

    conn = sqlite3.connect(DB)

    c = conn.cursor()


    c.execute("""
    CREATE TABLE IF NOT EXISTS proposals(
        fingerprint TEXT PRIMARY KEY,
        dossier_id TEXT,
        action TEXT,
        call_id TEXT,
        proposal TEXT
    )
    """)


    c.execute("""
    CREATE TABLE IF NOT EXISTS evaluations(
        evaluation_id TEXT PRIMARY KEY,
        digest TEXT,
        receipt_key TEXT
    )
    """)


    c.execute("""
    CREATE TABLE IF NOT EXISTS commits(
        receipt_id TEXT PRIMARY KEY,
        result TEXT
    )
    """)


    conn.commit()
    conn.close()



init_db()



# -------------------------
# Models
# -------------------------

class RequestBody(BaseModel):

    operation: str

    evaluationId: str | None = None

    dossiers: list | None = None

    receipts: list | None = None



# -------------------------
# Helpers
# -------------------------

def fingerprint(data):

    text = json.dumps(
        data,
        sort_keys=True,
        separators=(",", ":")
    )

    return hashlib.sha256(
        text.encode()
    ).hexdigest()



def fake_ai_decision(dossier):

    """
    Replace this with your AI model.
    This safe baseline avoids unsafe actions.
    """


    content = dossier.get(
        "content",
        ""
    ).lower()



    if (
        "ignore previous instructions" in content
        or "send secret" in content
        or "reveal" in content
    ):

        return {
            "action":
            "quarantine_item",

            "evidence":
            [
                "Message contains instructions attempting to control processing"
            ],

            "target": None,

            "payload": None
        }



    if "unsubscribe" in content:

        return {

            "action":
            "no_action",

            "evidence":
            [
                "Request is informational"
            ],

            "target": None,

            "payload": None
        }



    return {

        "action":
        "request_confirmation",

        "evidence":
        [
            "Identity or authorization requires confirmation"
        ],

        "target":
        "approval_queue",

        "payload":
        {
            "reason":
            "needs verification"
        }

    }



# -------------------------
# Main endpoint
# -------------------------

@app.post("/")
def agent(req: RequestBody):


    if req.operation not in [
        "propose",
        "commit"
    ]:

        raise HTTPException(
            400,
            "invalid operation"
        )


    # =====================
    # PROPOSE
    # =====================

    if req.operation == "propose":


        if not req.dossiers:

            raise HTTPException(
                400,
                "missing dossiers"
            )


        conn = sqlite3.connect(DB)

        c = conn.cursor()


        proposals=[]


        for dossier in req.dossiers:


            if "id" not in dossier:

                raise HTTPException(
                    400,
                    "missing dossier id"
                )


            fp = fingerprint(
                dossier
            )


            c.execute(
                """
                SELECT proposal
                FROM proposals
                WHERE fingerprint=?
                """,
                (fp,)
            )


            row=c.fetchone()



            if row:

                proposal=json.loads(
                    row[0]
                )


            else:


                proposal = fake_ai_decision(
                    dossier
                )


                call_id = hashlib.sha256(
                    (
                    fp+
                    str(time.time())
                    ).encode()
                ).hexdigest()


                proposal["callId"]=call_id


                c.execute(
                    """
                    INSERT INTO proposals
                    VALUES(?,?,?,?,?)
                    """,
                    (
                    fp,
                    dossier["id"],
                    proposal["action"],
                    call_id,
                    json.dumps(proposal)
                    )
                )



            proposals.append(
                proposal
            )


        digest=fingerprint(
            proposals
        )


        c.execute(
            """
            INSERT OR REPLACE INTO evaluations
            VALUES(?,?,?)
            """,
            (
            req.evaluationId,
            digest,
            ""
            )
        )


        conn.commit()
        conn.close()



        return {

            "status":
            "awaiting_receipts",

            "proposals":
            proposals
        }




    # =====================
    # COMMIT
    # =====================


    if req.operation=="commit":


        if not req.receipts:

            raise HTTPException(
                400,
                "missing receipts"
            )


        conn=sqlite3.connect(DB)

        c=conn.cursor()


        outcomes=[]


        for receipt in req.receipts:


            receipt_id = receipt.get(
                "receiptId"
            )


            if not receipt_id:

                raise HTTPException(
                    400,
                    "invalid receipt"
                )


            c.execute(
                """
                SELECT result
                FROM commits
                WHERE receipt_id=?
                """,
                (receipt_id,)
            )


            existing=c.fetchone()



            if existing:

                outcomes.append(
                    json.loads(existing[0])
                )

                continue



            result={

                "receiptId":
                receipt_id,

                "status":
                "accepted"

            }


            c.execute(
                """
                INSERT INTO commits
                VALUES(?,?)
                """,
                (
                receipt_id,
                json.dumps(result)
                )
            )


            outcomes.append(
                result
            )



        conn.commit()
        conn.close()



        return {

            "status":
            "completed",

            "outcomes":
            outcomes

        }