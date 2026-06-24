# The Rustic Slice - AI WhatsApp Agent 🍕🤖

An intelligent, hybrid-architecture WhatsApp chatbot built for a restaurant. This bot combines the conversational power of Large Language Models (Groq/Llama-3) with strict Python backend logic to handle dynamic ordering, real-time cart math, and edge-case management.

## Features
* **Conversational Ordering:** Natural language processing to understand user intent, add items, and answer menu questions.
* **Hybrid Native UI:** Seamlessly integrates Meta's native WhatsApp interactive buttons and lists for browsing the menu visually.
* **Strict Cart Math:** Bypasses LLM hallucinations by using a Python-driven SQLite database to calculate mathematically perfect receipts and dynamic discounts (e.g., free sauces with wings).
* **State Management:** Tracks active sessions, user carts, and contextual history in-memory.

## Demo
Here is the bot in action:

![WhatsApp Chat Demonstration](ss.jpg)
![WhatsApp Chat Demonstration](ss2.jpg)
![WhatsApp Chat Demonstration](ss3.jpg)

## Tech Stack
* **Backend:** Python, FastAPI
* **AI/LLM:** Groq API (Llama-3.1-8b-instant)
* **Database:** SQLite (Local, serverless)
* **Integration:** Meta Graph API (WhatsApp Business)

## Local Setup
1. Clone the repository.
2. Install dependencies: `pip install fastapi uvicorn requests groq`
3. Create a `wa-token` file to store your Meta/Groq API keys safely.
4. Run the server: `uvicorn main:app --reload`
5. Expose your local server using ngrok or a similar tunneling service, and paste the webhook URL into your Meta Developer Console.
