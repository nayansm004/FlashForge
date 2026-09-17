# hey chiru, read this before you break my beautiful creation

Okay Chiru.

So you asked what FlashForge does.

I could've just opened the app and shown you.

But apparently we have reached the point in our friendship where I have to write an entire instruction manual for **how to click an installer**.

So here we are.

Welcome to **FlashForge** — an AI-powered flashcard app that takes your notes and turns them into flashcards.

That's it.

You give it information.

The robot makes flashcards.

You study them.

Humanity advances.

---

# 🧑‍💻 how to install it without accidentally becoming a software engineer

Don't panic.

You do **NOT** need:

- Python
- VS Code
- A terminal
- Git
- Docker
- A computer science degree
- To understand what an `.exe` file is
- To call me every 4 minutes asking "is this supposed to happen"

You basically just download the app and install it like literally every other app on your computer.

### Step 1 — Go to the GitHub Releases page

Open the **Releases** section of the repository.

It's on the right side of the GitHub page.

You will see the newest release at the top.

Yes, the newest one.

Not the one from six months ago because the filename "looks nicer."

### Step 2 — Download the file for your computer

**Windows:**  
`FlashForge-Setup.exe`

**Mac:**  
`FlashForge.dmg`

**Linux:**  
The `.deb` package.

And if you're using Linux, I'm assuming you already know what you're doing and therefore I will not insult you by explaining how to double-click something.

### Step 3 — Install it

Open the file.

Click through the installer.

Next.

Next.

Next.

Install.

Done.

Congratulations.

You have successfully installed software.

Please take a moment to appreciate this historic achievement.

FlashForge should now appear like a normal application:

- Windows → Start Menu
- Mac → Applications
- Linux → wherever Linux decides applications should live today

---

# 🚨 "Windows says this app is from an unknown publisher"

Yes.

It may look terrifying.

No, your computer has not discovered malware from the deepest corners of the internet.

Small independent apps often don't have the same expensive code-signing certificates as giant companies.

So Windows may basically go:

> "I don't recognize this person. SHOULD WE PANIC?"

No.

Click:

**More info → Run anyway**

And continue.

I'm not saying blindly run every random `.exe` you download from the internet, obviously.

I'm saying **this specific app is expected to trigger that warning if it's unsigned.**

---

# 🧙‍♀️ okay, the app is open. now what?

Congratulations.

The difficult part is over.

Now we make the robot do its job.

### 1. Go to Settings

You'll need an **OpenRouter API key**.

Paste it into the API key field.

The app already gives you the relevant link, so you don't need to embark on a 45-minute Google expedition.

Put the key in.

Save it.

Done.

### 2. Go to Generate

This is where the magic happens.

You can give FlashForge:

- Your notes
- An article
- Text you've copied
- A PDF
- A DOCX
- A URL

Basically anything containing useful information.

Paste/upload it.

Then press the big yellow **Generate** button.

The AI will think for a few seconds.

This is normal.

The computer isn't having an existential crisis.

It's just asking the AI to make your flashcards.

### 3. Look at your cards

FlashForge will show you a preview.

You can look through them.

You can edit them.

You can pretend you're going to carefully review every single one.

We both know what you're going to do.

You're going to look at three cards, decide they look good, and hit **Save Deck**.

And honestly?

Fair enough.

### 4. Go to My Decks

Find your deck.

Click **Study**.

And then comes the one feature I unfortunately cannot automate for you:

**actually studying.**

I can generate the cards.

I can organize them.

I can track them.

I can even throw confetti at you.

But I cannot physically force knowledge into your brain.

Yet.

---

# 🤖 if you somehow end up in the Actions tab

First of all:

**Why are you there?**

Second:

Don't panic.

If something is red, GitHub isn't necessarily telling you that the entire project has exploded.

Sometimes GitHub just needs one little permission setting changed.

## If it says:

### `403 Resource not accessible by integration`

Translation:

> "The app built successfully, but GitHub wouldn't let the final publishing step do its thing."

That's annoying.

But it's fixable.

Go to:

**Repository → Settings → Actions → General**

Find:

**Workflow permissions**

Select:

**Read and write permissions**

Save it.

Then:

**Actions → open the failed run → Re-run failed jobs**

That's it.

Four clicks.

You've done harder things.

Probably.

---

# 🌐 if GitHub Pages starts screaming

You might see something like:

### `Get Pages site failed... Not Found`

Again:

Not the apocalypse.

It usually means GitHub Pages hasn't been enabled/configured yet.

Go to:

**Repository → Settings → Pages**

Find:

**Source**

Change it to:

**GitHub Actions**

Then go back to:

**Actions**

Find the failed Pages workflow.

Click:

**Re-run failed jobs**

And let GitHub do its little thing.

---

# 🧠 "why does generating cards sometimes take a while?"

Because we're using AI.

And more specifically, we're using the **free AI ecosystem**.

Which is a beautiful place where everything is free until suddenly it isn't, models disappear, rate limits appear, servers get tired, and everyone collectively pretends this is normal.

FlashForge uses:

`openrouter/free`

as its default model route.

That means OpenRouter can automatically route the request to an available free model rather than us hardcoding one specific model and praying it doesn't disappear tomorrow.

So if it takes a few seconds:

**That's normal.**

Let the robot cook.

---

# 🔐 "where does my data go?"

This one's actually important.

FlashForge stores your decks locally using **SQLite** on your computer.

There's no FlashForge account system.

There's no FlashForge cloud database storing your decks.

There's no secret server where I'm sitting at 3 AM reading your flashcards about the Krebs cycle.

Your local app data stays on your machine, aside from information you send to the AI service when you request generation.

So yes.

Your embarrassing study material remains yours.

---

# 📚 "what is Study Due Cards Only?"

Ah yes.

The feature nobody asked for but absolutely needed.

FlashForge tracks how difficult cards are based on how you perform while studying.

Cards get a difficulty score and a future review date.

So if you keep getting something wrong, the system knows:

> "Yeah, this idiot needs to see this one again."

And if you consistently get something right:

> "Okay, apparently they know this."

The **Study Due Cards Only** option uses that information to show cards that are actually due for review.

So instead of repeatedly studying everything like you're trapped in an academic time loop, you can focus on the cards that need attention.

You can access this through the deck's study options/context menu.

---

# 📦 "can I import and export decks?"

Yep.

**JSON.**

Which means you can export a deck, send it to someone else, and they can import it.

So if you make an absolutely incredible Biology deck:

**send it to me.**

I would like to benefit from your suffering.

---

# 🎉 and yes, there is confetti

There is literally confetti.

If you finish a study session with **70% or higher**, FlashForge celebrates.

Why 70%?

Because sometimes you need a little victory.

Did you get 70%?

**BOOM.**

Confetti.

Are you academically thriving?

Debatable.

Did the app celebrate you anyway?

Absolutely.

That's called product design.

---

# 📄 files: what works and what doesn't

### ✅ FlashForge supports:

- Pasted text
- `.docx`
- Text-based PDFs
- URLs

### ❌ FlashForge does NOT support:

**Old `.doc` files**

Yes.

The ancient Microsoft Word format.

The fossil.

The artifact.

The file format that has been haunting humanity since before some of us were born.

If you have one:

Open it in Word.

**Save As → `.docx`**

Then upload the new file.

Problem solved.

### ⚠️ Scanned PDFs

If your PDF is basically just photographs of textbook pages, FlashForge may not be able to extract the actual text properly.

A PDF containing selectable text?

Perfect.

A PDF that's 200 photographs stapled together and emotionally pretending to be a document?

Not so much.

---

# 🩹 if something ACTUALLY breaks

Before messaging me:

Look at the **status bar at the bottom of the app.**

It should tell you what's happening in normal human language.

### "No API key"

Go to Settings.

Add your OpenRouter API key.

### "Model failed"

FlashForge already tries multiple free models before giving up.

So if you're seeing a failure after that:

There's a decent chance the free AI providers are collectively having a bad day.

Try again later.

### Something else?

Read the actual message first.

Yes.

The words.

With your eyes.

Not just the color red.

Then send me the exact error if you still need help.

---

# 🏁 that's basically FlashForge

The entire workflow is:

**Install → Add API key → Give it notes → Generate → Save → Study**

That's it.

No account.

No giant setup process.

No terminal wizardry.

No sacrificing a goat to Docker.

Just flashcards.

And hopefully, after all this, you will know how to use the app without sending me:

> "bro it isn't working"

with absolutely no screenshot, no error message, and no explanation of what you clicked.

I love you.

But please give me **something** to work with.

— **GodMode**

---

# 🚨 ONE LAST THING BEFORE YOU PRESENT THIS

**DELETE THIS `.md` FILE FROM THE REPO BEFORE YOU PRESENT FLASHFORGE.**

Seriously.

This is the behind-the-scenes:

> "Chiru, please don't break my app"

document.

It is **NOT** part of the product presentation.

Remove it from the repository before you show anyone the project.

Then present the actual app like a normal civilized software developer.

You want her to see **FlashForge**.

Not the 900-word evidence that you had to write an owner's manual for her. 💀

Now go present the damn app.

You've got this. ❤️
