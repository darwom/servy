import aiohttp
import config
import time


class LambdaChatService:
    def __init__(self, bot):
        self.bot = bot
        self.session = aiohttp.ClientSession()
        self.target_channel_id = 840026592142688303
        self.system_prompt = """
[systemprompt]
Du bist LogicGPT: Ein KI-System für rigoroses analytisches Denken. Dein Fokus liegt auf der systematischen Zerlegung von Problemen und der kritischen Hinterfragung JEDER Annahme.

### DENKPROZESS-REGELN:

1. **Fundamentale Analyse** [!]
   - Liste ALLE expliziten Informationen
   - UNTERSCHEIDE zwischen:
     * Bruttowerten (vor Verlusten)
     * Nettowerten (nach Verlusten) [!]
   - Identifiziere Wechselwirkungen:
     * Wenn A gewinnt, verliert B
     * Wenn B verliert, reduziert das seinen Nettogewinn

2. **Kausale Verkettung** [!]
   - Stelle Wenn-Dann-Beziehungen auf
   - Verfolge ALLE Konsequenzen
   - Prüfe Rückwirkungen und Kreisschlüsse
   - Verifiziere JEDE logische Verbindung

3. **Mathematische Modellierung** [!]
   - Definiere präzise Variablen
   - Stelle Gleichungssysteme auf
   - Berücksichtige ALLE Abhängigkeiten
   - Prüfe Einheiten und Dimensionen

4. **Systematische Validierung** [!]
   PRÜFE:
   - Sind die Vorzeichen korrekt?
   - Stimmen Netto/Brutto Beziehungen?
   - Funktioniert die Umkehrrechnung?
   - Bleiben Erhaltungsgrößen konstant?

5. **Kritische Reflexion** [!]
   FRAGE:
   - Was wurde übersehen?
   - Welche Annahmen sind versteckt?
   - Wo könnten Denkfehler sein?
   - Ist das Ergebnis plausibel?

### ANTWORTFORMAT:

[reasoning]
1. PROBLEMZERLEGUNG:
   - Explizite Fakten: ...
   - Implizite Folgen: ... [!]
   - Wechselwirkungen: ... [!]

2. ANALYSE:
   - Brutto vs Netto: ... [!]
   - Wenn A, dann B, weil: ...
   - Rückwirkung auf A: ...

3. BERECHNUNG:
   - Variablen & Einheiten: ...
   - Gleichungen: ...
   - Zwischenschritte: ... [!]
   - Kontrolle: ... [!]

4. VALIDIERUNG:
   □ Vorzeichen geprüft
   □ Einheiten konsistent
   □ Netto = Brutto - Verluste
   □ Umkehrrechnung funktioniert
   □ Extremfälle plausibel

[answer]
Präzise, mehrfach validierte Antwort.

### KRITISCHE PRINZIPIEN:

[!] Unterscheide IMMER zwischen Brutto und Netto
[!] Verfolge ALLE Wechselwirkungen
[!] Prüfe JEDEN Schritt mehrfach
[!] Suche AKTIV nach Fehlern
[!] Validiere ALLE Annahmen

[/systemprompt]
"""
        self.model = "hermes3-70b"
        self.temperature = 0.2
        self.top_p = 0.2
        self.context = [{"role": "system", "content": self.system_prompt}]
        bot.add_listener(self.on_message)

    async def send_response(self, channel, content):
        chunks = [content[i : i + 2000] for i in range(0, len(content), 2000)]
        for chunk in chunks:
            await channel.send(chunk)

    async def on_message(self, message):
        if message.channel.id != self.target_channel_id:
            return

        if message.author == self.bot.user:
            return

        # Send "Thinking..." message
        thinking_message = await message.channel.send("`Thinking...`")
        start_time = time.time()

        # Generate response
        response = await self.send_to_lambda(message.content)

        end_time = time.time()
        elapsed_time = end_time - start_time

        if response:
            # Extract answer after [answer] tag
            answer = self.extract_answer(response)

            # Edit message to show thought duration and answer
            new_content = f"`Thought for {elapsed_time:.1f} seconds:`\n\n{answer}"
            await thinking_message.edit(content=new_content)

            # Append only the answer to context
            self.context.append({"role": "assistant", "content": answer})

    async def send_to_lambda(self, user_message):
        url = config.LAMBDA_API_URL
        headers = {
            "Authorization": f"Bearer {config.LAMBDA_API_KEY}",
            "Content-Type": "application/json",
        }

        # Add user message to context
        self.context.append({"role": "user", "content": user_message})

        # Limit context to system prompt + last 2 message pairs
        if len(self.context) > 5:  # system prompt + 2 pairs = 5 messages
            filtered_context = [
                self.context[0],  # Keep system prompt
                *self.context[-4:],  # Keep last 2 user-assistant pairs
            ]
            self.context = filtered_context

        payload = {
            "model": self.model,
            "messages": self.context,
            "temperature": self.temperature,
            "top_p": self.top_p,
        }

        try:
            async with self.session.post(url, headers=headers, json=payload) as resp:
                if resp.status == 200:
                    data = await resp.json()

                    # Log token usage
                    usage = data.get("usage", {})
                    prompt_tokens = usage.get("prompt_tokens", 0)
                    completion_tokens = usage.get("completion_tokens", 0)
                    total_tokens = usage.get("total_tokens", 0)
                    print(
                        f"Tokens used - Prompt: {prompt_tokens}, Completion: {completion_tokens}, Total: {total_tokens}"
                    )

                    assistant_message = data["choices"][0]["message"]["content"]

                    # Add assistant response to context
                    self.context.append(
                        {"role": "assistant", "content": assistant_message}
                    )

                    # Limit context size
                    if len(self.context) > 10:
                        self.context = [self.context[0]] + self.context[-9:]

                    return assistant_message
                else:
                    return f"Error: Lambda API returned {resp.status}"
        except Exception as e:
            return f"Error communicating with Lambda API: {e}"

    def extract_answer(self, assistant_message):
        print(assistant_message)
        # Find the [answer] tag
        answer_start = assistant_message.find("[answer]")
        if answer_start != -1:
            # Extract text after [answer] tag
            answer = assistant_message[answer_start + len("[answer]") :].strip()
            # Remove potential [/answer] tag
            answer = answer.replace("[/answer]", "").strip()
            return answer
        else:
            # If tag not found, return the full message
            return assistant_message

    async def close(self):
        await self.session.close()
