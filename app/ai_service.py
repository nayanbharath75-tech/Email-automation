import os
import json
from openai import AsyncOpenAI

class AIService:
    def __init__(self):
        self.client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    
    async def analyze_email(self, subject: str, body: str) -> dict:
        """Analyze email content and determine importance and required action"""
        try:
            prompt = f"""
            Analyze this email and return JSON with:
            - is_important: boolean (true if urgent, business-critical, or requires immediate attention)
            - needs_reply: boolean (true if a response is expected)
            - summary: brief summary of email content
            - category: one of [business, personal, spam, notification, other]
            
            Subject: {subject}
            Body: {body[:1000]}
            
            Return ONLY valid JSON.
            """
            
            response = await self.client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3
            )
            
            result = json.loads(response.choices[0].message.content)
            return result
        except Exception as e:
            print(f"AI analysis error: {e}")
            return {
                "is_important": False,
                "needs_reply": False,
                "summary": "Analysis failed",
                "category": "other"
            }
    
    async def generate_reply(self, subject: str, body: str) -> str:
        """Generate an appropriate email reply"""
        try:
            prompt = f"""
            Generate a professional, polite email reply based on this email.
            Keep it concise (2-3 sentences) and appropriate for the context.
            
            Subject: {subject}
            Body: {body[:1000]}
            
            Reply:
            """
            
            response = await self.client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7,
                max_tokens=150
            )
            
            return response.choices[0].message.content
        except Exception as e:
            print(f"Reply generation error: {e}")
            return "Thank you for your email. I'll get back to you as soon as possible."