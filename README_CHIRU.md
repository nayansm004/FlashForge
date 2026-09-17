# hey chiru, read this before you break it

Okay so. You asked what this thing does. I could've just shown you, but no — you get the full write-up, because apparently that's the tax for being friends with someone who builds software instead of, I don't know, going outside.

This is FlashForge. It makes flashcards. From your notes. Using AI. That's it. That's the whole pitch. I know, groundbreaking, hold your applause.

## how to not break it

1. Run `python main.py`. If it explodes immediately, you're missing PyQt6, and yes, `pip install -r requirements.txt` exists for a reason, use it.
2. Go to **Settings**. Paste in an OpenRouter API key. It's free, it takes two minutes, and I already put the link in there so you have no excuse.
3. Go to **Generate**. Paste some text — your notes, an article, whatever — or upload a PDF/DOCX, or just throw a URL at it. Hit the big yellow button. Watch it think.
4. Cards appear. You get a little preview so you can pretend you're going to check them all before saving. You won't. Hit **Save Deck**.
5. Go to **My Decks**, hit **Study**, and actually study, Chiru. This part's on you, I can't fix that with code.

## the part where I explain myself so you stop asking

- **Why does it take a few seconds sometimes?** Because it's calling a *free* AI model, and free means "there's a line," so it waits politely between requests instead of getting us both rate-limited and banned. You're welcome.
- **What if the AI model breaks / gets deleted / whatever?** I set the default to `openrouter/free`, which is OpenRouter's own "just pick something that's alive right now" router, specifically so I don't have to babysit a hardcoded model name every time OpenRouter reshuffles their free tier (which, apparently, is often, because nothing free stays free forever, chiru, remember that).
- **Where does my data go?** Nowhere. It's a SQLite file sitting on your own computer. No account, no cloud, no me reading your embarrassing "explain mitochondria like I'm five" flashcards.
- **Why is there a "Study Due Cards Only" option I didn't ask for?** Because every card you get right or wrong quietly adjusts a difficulty score and a "come back later" date, and originally that data was being calculated and then completely ignored, like a gym membership. Now it's actually used. Right-click a deck, thank me later.
- **Can I import/export decks?** Yes. JSON files. So if you make a genuinely good Biology deck, you can send it to me and I won't have to make my own, which — let's be honest — is the actual reason this feature exists.
- **There's confetti?** There's confetti. If you score 70%+ at the end of a study session, the app throws a tiny party for you. Set the bar low, feel like a winner. Design philosophy, really.

## things that will and will not work

- **Will work:** pasting text, uploading a real `.docx` (the modern kind), uploading a PDF that has actual text in it (not a scanned photo of a textbook, come on).
- **Will NOT work:** ancient `.doc` files from 2003. Word can Save As `.docx` in one click. Do that. I put a real error message for this specifically so you'd stop asking me why it "doesn't work" — it's not broken, your file format is just old.
- **Also will not work:** studying without opening the app. Shocking, I know.

## if it's actually broken (not just you)

Check the status bar at the bottom — it tells you what went wrong in plain English, not some cursed stack trace. If it says "No API key," go add one. If it says a model failed, it's already trying seven other free models before giving up, so if you're seeing that error, the whole free tier is having a moment, not just us.

Anyway. Go make flashcards instead of texting me questions I already answered above. Love you, mean it, this document is proof I tried.

— GodMode
