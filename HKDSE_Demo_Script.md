# DeepTutor × HKDSE — Demo Video Script (5-minute version)

> Version: DeepTutor v1.4.2 + custom Market / HKDSE module
> URL: http://localhost:3782
> Target length: **~5 minutes** (Chapter 1 ~1 min, Chapter 2 ~3.5 min, intro/outro ~0.5 min)
> Narration: casual spoken English. The running time after each line is a rough guide.
>
> Before recording:
> - [ ] Backend + frontend running (you can see **Market** in the sidebar)
> - [ ] DeepSeek (LLM) has credit, Jina (Embedding) is set up
> - [ ] 3 knowledge bases ready: `hkdse-chinese` / `hkdse-english` / `hkdse-maths`
> - [ ] Copy the "Sample input" blocks into a notepad so you can paste fast
> - [ ] To stay near 5 min, pre-generate the Chinese paper once so it's cached, or speed up that clip in editing

---

## Opening (0:00 – 0:15)

> "Hi everyone. This is a smart tutoring system we built on top of the open-source project **DeepTutor**.
> DeepTutor is an AI tutoring platform from the HKU Data Intelligence Lab, and what we added is a
> **Market module for the Hong Kong DSE exam**. Quick tour first, then we'll focus on the part we built."

---

# Chapter 1 — Quick Platform Tour (0:15 – 1:15)

> Keep this fast. One smooth pass, don't stop to wait for anything.

### Sidebar tour (0:15 – 0:50)

**On screen**: home page → slowly mouse over each sidebar item as you mention it → click **Chat**
and ask the question below to show a live answer.

**Sample input (Chat)**:
```
In one sentence, what is a quadratic equation?
```

> "On the left is the navigation, so let's quickly run through it.
> **Chat** is the main workspace — we can ask a question and get an answer, and modes like deep solving
> and quiz making all share the same conversation.
> **TutorBot** lets us build tutors that each have their own memory and skills.
> **Co-Writer** is a writing space where the AI helps us draft and edit.
> **Book** turns our materials into interactive study books.
> **Knowledge** is where we upload documents to build knowledge bases,
> and **Memory** keeps track of how we learn over time.
> These are the platform's general features — now let's get to the part we focused on."

### Settings — LLM and Embedding keys (0:50 – 1:15)

**On screen**: **Settings → Catalog**, point at the LLM card, then the Embedding card.

> "One thing worth a quick look — the Settings. In the model catalog we set up two things.
> For the **LLM** we're using DeepSeek — just the API key and the model name; this does all the
> generating and grading. For the **Embedding** model we're using Jina — this turns documents into
> vectors, which is what makes the knowledge base work. Set these two and you're good to go."

> "Okay, that's the open-source part. Now the part we built — the **Market**."

---

# Chapter 2 — Market and the HKDSE Features (1:15 – 4:45)

### Market overview (1:15 – 1:35)

**On screen**: click **Market**, move your mouse across the cards.

> "This is the **Market** we added. The idea is to turn each exam task into its own app.
> The main part is this group — **HKDSE Subjects, the Hong Kong DSE exam** — with dedicated tools
> for Chinese, English, and Math. Let's go through them."

---

### 2.1 Chinese (1:35 – 2:35)

**On screen**: **HKDSE → Chinese** — show the three cards quickly.

> "Chinese has three tools: Paper Generator, Essay Grader, and a Classical Chinese Analyzer."

**Hero demo — Paper Generator with the knowledge base (1:40 – 2:25)**

**On screen**: click **Paper Generator** → **point at the "Knowledge Base" dropdown**, pick
`hkdse-chinese` → pick a passage type → generate → let it stream.

> "The best part is this one — it's connected to a knowledge base.
> See this dropdown? We uploaded the 2012 DSE Chinese past papers into a knowledge base called
> `hkdse-chinese`. When we pick it, the system first pulls real passages from those papers,
> then builds a reading paper that feels like the real exam.
> It's streaming in now — a full passage, multiple choice and short answer, and every question
> comes with a model answer and an explanation. This is the difference from just using plain ChatGPT —
> it's grounded in real past papers."

**Quick mention (2:25 – 2:35)**

> "The other two — Essay Grader and the Classical Chinese Analyzer — grade essays on the official
> rubric and translate classical Chinese line by line. We'll show grading in English next."

---

### 2.2 English (2:35 – 3:25)

**On screen**: **HKDSE → English** — show the three cards.

> "English has the same Paper Generator, plus an Essay Coach and an Integrated Skills simulator."

**Hero demo — Essay Coach (fast, live) (2:40 – 3:15)**

**On screen**: click **Essay Coach** → paste the essay below → pick the genre → submit (this one is quick).

**Sample input (English essay — paste as is)**:
```
Title: Should Smartphones Be Allowed in Schools?

Smartphones are a big part of modern life, and whether they belong in schools is a hot debate.

On one hand, they are useful learning tools. Students can look things up instantly and contact
teachers, and in an emergency they can reach their parents.

On the other hand, phones can be a real distraction. Some students play games or scroll social
media in class, which hurts their focus.

In my opinion, a balanced approach is best. Schools should allow phones for learning under teacher
supervision, but limit them during lessons.
```

> "The Essay Coach grades on the official DSE Paper 2 standard — Content, Language, and Organisation.
> It gives a score and a comment for each one, plus the strengths and what to improve.
> A student gets full feedback in seconds, no waiting for a teacher."

**Quick mention (3:15 – 3:25)**

> "The Paper Generator here works just like Chinese — and it even includes the DSE's Summary Writing
> question type. There's also an Integrated Skills simulator that walks through the Paper 3 format."

---

### 2.3 Math (3:25 – 4:25)

**On screen**: **HKDSE → Math** — show the three cards.

> "And Math has a Paper Generator, a Step Checker, and Topic Drill."

**Hero demo — Step Checker (fast, with a mistake on purpose) (3:30 – 4:15)**

**On screen**: click **Step Checker** → type the question → enter the steps below
(**second line is wrong on purpose**) → submit.

**Sample input (question)**:
```
Solve the equation: 3x - 7 = 2x + 5
```

**Sample input (student steps — second line is wrong on purpose)**:
```
3x - 2x = 5 + 7
x = 13
```

> "This is the one we really like. The student types their working line by line,
> and the system checks each line and finds the first mistake.
> We put an error on the second line on purpose — x should be 12, not 13 — let's see if it catches it.
> There it is — it points to the exact step that's wrong and gives the correct answer.
> Great for teaching students to be careful with their working."

**Quick mention (4:15 – 4:25)**

> "Topic Drill makes practice questions by DSE syllabus topic, and Math can also build full papers
> from the past-paper knowledge base, same as the other subjects."

---

## Closing (4:25 – 4:50)

**On screen**: back to the Market home page, mouse over the three HKDSE subjects.

> "So that's it. On top of the open-source DeepTutor platform, we added a Market module for the HKDSE —
> three subjects, each with its own tools: paper generation backed by real past papers,
> essay grading on the official rubric, and step-by-step checking.
> It takes a general AI model and makes it fit the real Hong Kong DSE exam. Thanks for watching!"

---

## Demo order cheat sheet (15 steps, ~5 min)

| # | Page | Action | Uses KB | Time |
|---|---|---|---|---|
| 1 | Home | mouse over sidebar | — | 0:15 |
| 2 | Chat | ask one question | — | 0:20 |
| 3 | TutorBot | show the list | — | 0:35 |
| 4 | Settings→Catalog | show LLM / Embedding | — | 0:50 |
| 5 | Market home | mouse over cards | — | 1:15 |
| 6 | Chinese hub | show 3 cards | — | 1:35 |
| 7 | Chinese→Paper Generator | pick `hkdse-chinese`, generate | ✅ | 1:40 |
| 8 | (say) Essay Grader + Analyzer | one-line mention | — | 2:25 |
| 9 | English hub | show 3 cards | — | 2:35 |
| 10 | English→Essay Coach | paste essay, grade | — | 2:40 |
| 11 | (say) Paper Generator + Integrated | one-line mention | — | 3:15 |
| 12 | Math hub | show 3 cards | — | 3:25 |
| 13 | Math→Step Checker | steps with a mistake | — | 3:30 |
| 14 | (say) Topic Drill + Paper Gen | one-line mention | — | 4:15 |
| 15 | Market home | closing | — | 4:25 |

## To hit 5 minutes

- **One hero demo per subject**, the rest is a single spoken line — that's the whole trick.
- **The Chinese paper takes 30–60 sec to stream.** Either pre-generate it so it loads instantly,
  or speed that clip up in editing. The English grading and Math step-check are only a few seconds,
  so those are safe to do live.
- If you're running long, cut the TutorBot line in Chapter 1 first.
- If you're running short, let the Chinese paper stream play out a few extra seconds.
