# Demo video script (1:50 max)

No music needed (if you add some, use only royalty-free audio). Show only MatchMind's fictional
clubs; never show real league names, logos or footage. Record the browser at 1440x900 with a
screen recorder (Windows: Xbox Game Bar, `Win + Alt + R`, or OBS).

Before recording, open these tabs so you can switch without loading delays:

1. https://alisaeed-1.github.io/matchmind/?match=mm-0004-comeback&seek=56&audience=fan
2. https://alisaeed-1.github.io/matchmind/?match=mm-0004-comeback&seek=56&audience=analyst&drawer=1
3. https://alisaeed-1.github.io/matchmind/?match=mm-0004-comeback&recap=1
4. https://alisaeed-1.github.io/matchmind/?match=mm-0004-comeback&seek=100&ask=1 (Ask MatchMind)

| Time | Screen | Voice-over (read naturally) |
|---|---|---|
| 0:00–0:10 | Home page | "Match graphics tell you *what* happened. MatchMind tells you *why it matters*, and tells each viewer in their own way." |
| 0:10–0:40 | Tab 1. Press play at 30x. Rovers score at 60' (about 13 s after pressing play): goal cards slide in over the pitch. | "A team of AI agents watches a live match. A Stats agent computes every number through an MCP server. A Producer decides which moments deserve the full team. The Insight agent explains why a moment matters, and the Narrator commentates." |
| 0:40–1:05 | Pause just after a card appears. Click **Analyst**, then **Fan**, then **Analyst** again. | "Same moment, two audiences. Fans get the emotion; analysts get xG, pressing and momentum. The Personalizer agent wrote both, and a Verifier checked every number against the stats. Nothing is invented." |
| 1:05–1:15 | Tune icon → language **اردو**, then back to English. Then tab 4 (Ask MatchMind): open "How did Rivermouth Rovers come back to win?". | "It speaks Urdu and Arabic. And you can just ask: a GitHub Copilot agent answers by calling the same stats tools over MCP. You can see which tools it used." |
| 1:15–1:35 | Tab 2 (handoff drawer). Scroll the list; point at a **retry** and a **fallback** row. | "Every handoff is logged. When a model gives a wrong number, the Verifier sends it back. When a model is rate-limited, we fall back to the next one, down to Microsoft Foundry Local on-device, and finally to verified templates. The broadcast never stops." |
| 1:35–1:45 | Tab 3 (recap). Scroll the turning points. | "At full time, the Narrator writes the recap: Rovers from two down to win three-two." |
| 1:45–1:50 | Back to the pitch view. | "MatchMind. Built with the Microsoft Agent Framework. Explainable, personal, and resilient." |

**Optional live segment** (replace 1:15–1:35 if the backend is running): Live agents mode, open the
hub drawer, flip **Simulate model outage**, and show `provider_fallback` → `fallback` rows and
the circuit breaker appearing in real time.
