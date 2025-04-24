from flask import Flask, request, jsonify, render_template
from werkzeug.utils import secure_filename
import os
import fitz  # PyMuPDF
import pytesseract
from PIL import Image
from dotenv import load_dotenv
from openai import OpenAI

# 환경 변수 로드
load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=OPENAI_API_KEY)

# Flask 설정
app = Flask(__name__)
UPLOAD_FOLDER = 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# 허용 확장자
ALLOWED_EXTENSIONS = {'pdf', 'png', 'jpg', 'jpeg'}

# 전역 상태 저장
latest_extracted_text = ""
uploaded_filenames = []

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def extract_text_from_pdf(path):
    text = ""
    try:
        with fitz.open(path) as doc:
            for page in doc:
                text += page.get_text()
    except Exception as e:
        print(f"[PDF 오류] {e}")
    return text.strip()

def extract_text_from_image(path):
    try:
        img = Image.open(path)
        text = pytesseract.image_to_string(img, lang='eng+kor')
        return text.strip()
    except Exception as e:
        print(f"[OCR 오류] {e}")
        return ""

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload_file():
    global latest_extracted_text, uploaded_filenames

    if 'file' not in request.files:
        return jsonify({'message': '파일이 없습니다.'}), 400

    files = request.files.getlist('file')
    if not files:
        return jsonify({'message': '선택된 파일이 없습니다.'}), 400

    combined_text = ""
    filenames = []

    for file in files:
        if file.filename == '' or not allowed_file(file.filename):
            continue

        filename = file.filename
        secure_name = secure_filename(filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], secure_name)
        file.save(filepath)

        ext = filename.rsplit('.', 1)[1].lower()
        if ext == 'pdf':
            combined_text += extract_text_from_pdf(filepath) + "\n"
        else:
            combined_text += extract_text_from_image(filepath) + "\n"

        filenames.append(filename)
        if filename not in uploaded_filenames:
            uploaded_filenames.append(filename)

    if not filenames:
        return jsonify({'message': '모든 파일이 무효하거나 업로드 실패'}), 400

    latest_extracted_text += "\n" + combined_text.strip()

    return jsonify({
        'message': '업로드 완료',
        'filenames': filenames
    }), 200

@app.route('/delete', methods=['POST'])
def delete_file():
    global latest_extracted_text, uploaded_filenames

    data = request.get_json()
    filename = data.get('filename')
    secure_name = secure_filename(filename)
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], secure_name)

    if os.path.exists(filepath):
        os.remove(filepath)
        uploaded_filenames = [f for f in uploaded_filenames if f != filename]
        latest_extracted_text = ""
        return jsonify({'message': f'{filename} 삭제됨'}), 200
    else:
        return jsonify({'message': '파일이 존재하지 않습니다.'}), 404

@app.route('/ask', methods=['POST'])
def ask():
    global latest_extracted_text
    data = request.get_json()
    question = data.get("question", "").strip()

    if not latest_extracted_text:
        return jsonify({'answer': '먼저 파일을 업로드 해주세요.'}), 400

    # ✅ 최대 길이 제한 (예: 4000자)
    context = latest_extracted_text[:4000]

    prompt = f"""다음 문서를 참고하여 질문에 답해주세요.

[문서 내용]
{context}

[질문]
{question}"""

    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",  # 필요 시 gpt-4로 변경 가능
            messages=[
                {"role": "system", "content": "당신은 문서를 분석하고 질문에 답하는 AI 비서입니다."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.5,
            max_tokens=1000
        )
        return jsonify({'answer': response.choices[0].message.content.strip()})
    except Exception as e:
        return jsonify({'answer': f"❌ GPT 오류: {e}"}), 500

if __name__ == '__main__':
    import os
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=False, host='0.0.0.0', port=port)

