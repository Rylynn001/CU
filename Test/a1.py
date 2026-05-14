from google import genai
client = genai.Client(
    vertexai=True,
    api_key="sk-UwY9rASEgQtecxbwGmA25nGSmMk2WnqX",
    http_options={
        "base_url": "https://modelhub.ailemac.com",
    },
)

response = client.models.generate_content(
    model='gemini-2.5-flash-image',
    contents='the blue sky with a bird'
)
for part in response.parts:
    if part.text is not None:
        print(part.text)
    elif image := part.as_image():
        image.save("D:/AAAA/output/gen2.png")