from flask import Flask, request, render_template, redirect, jsonify
import serial
import json
import os
import time

app = Flask(__name__)
DATA_FILE = 'data/product.json'  # 화장품 정보 저장 경로

# 아두이노와 시리얼 통신 설정 (COM 포트는 환경에 따라 변경 필요)
try:
    ser = serial.Serial('COM4', 9600, timeout=1)
except:
    ser = None  

# 최근 측정된 무게 및 측정 시간
last_weight = 0.0
last_checked_time = 0

# JSON 파일에서 화장품 정보 로딩
def load_product():
    if not os.path.exists(DATA_FILE):
        return None
    try:
        with open(DATA_FILE, 'r') as f:
            return json.load(f)
    except json.JSONDecodeError:
        return None 

# 화장품 정보를 JSON 파일에 저장
def save_product(product):
    with open(DATA_FILE, 'w') as f:
        json.dump(product, f, indent=2)

# 제품 등록 시 빠르게 무게를 측정 (등록 지연 방지용)
def get_quick_weight(timeout=2):
    if ser is None:
        return 0.0
    start = time.time()
    while time.time() - start < timeout:
        try:
            ser.flushInput()  # 버퍼 비우기
            line = ser.readline().decode().strip()
            weight = float(line)
            if weight > 0:  # 음수 또는 0은 무시
                return round(weight, 2)
        except:
            continue  # 파싱 실패 시 다음 줄로
    return 0.0

# 실시간 알림을 위한 안정적인 평균 무게 측정 함수
def get_stable_weight(samples=5, delay=0.2):
    if ser is None:
        return 0.0
    values = []
    for _ in range(samples):
        try:
            ser.flushInput()
            weight = float(ser.readline().decode().strip())
            if 10 < weight < 3000:  # 너무 작거나 큰 값은 노이즈로 간주
                values.append(weight)
        except:
            pass
        time.sleep(delay)  # 측정 간의 간격 설정
    if not values:
        return 0.0
    average = sum(values) / len(values)
    return round(average, 2)

# 메인 페이지: 제품 등록, 삭제, 무게 상태 확인 등 전반적 기능 수행
@app.route('/', methods=['GET', 'POST'])
def index():
    global last_weight, last_checked_time
    product = load_product()

    if request.method == 'POST':
        # 제품 삭제 요청 처리
        if 'delete' in request.form:
            if os.path.exists(DATA_FILE):
                os.remove(DATA_FILE)
            return redirect('/')
        # 임계값 업데이트 처리
        elif 'update' in request.form:
            threshold = int(request.form['threshold'])
            product = load_product()
            if product:
                product['threshold_percent'] = threshold
                save_product(product)
            return redirect('/')
        # 신규 제품 등록 요청 처리
        else:
            name = request.form['name']
            threshold = int(request.form['threshold'])
            weight = get_quick_weight()  # 빠르게 현재 무게 측정

            product = {
                'name': name,
                'initial_weight': weight,
                'threshold_percent': threshold
            }
            save_product(product)
            return redirect('/')

    # 현재 무게 측정은 5초 간격으로 제한 (과도한 측정 방지)-> 사용자가 화장품을 사용하는 시간을 5초로 간주하여 해당 시간 동안은 측정을 하지 않기로 한다.
    # 실제로 제품을 출시한다면 사용자가 화장품을 사용하는 시간을 고려하여 5~10분으로 측정해야 한다.
    now = time.time()
    if now - last_checked_time > 5:
        last_weight = get_stable_weight()
        last_checked_time = now

    current_weight = last_weight

    # 임계값 이하인지 확인하여 알림 조건 판단-> 부족하다는 알림을 보내도록 한다.
    alert = False
    if product:
        threshold_weight = product['initial_weight'] * (product['threshold_percent'] / 100)
        alert = current_weight < threshold_weight

    # index.html 렌더링 시 현재 상태 전달
    return render_template('index.html', product=product, current=current_weight, alert=alert)

@app.route('/current')
def current():
    global last_weight, last_checked_time
    product = load_product()

    # 5초에 한 번만 측정하여 성능 부담 완화한다. 너무 자주 측정할 경우 사용자가 잠시 화장품을 사용하기 위해 들어올릴경우 무게를 0으로 측정하는 오류가 발생할 수 있기 때문이다.
    now = time.time()
    if now - last_checked_time > 5:
        last_weight = get_stable_weight()
        last_checked_time = now

    current_weight = last_weight
    alert = False
    threshold = 0
    name = ''
    if product:
        threshold = product['initial_weight'] * (product['threshold_percent'] / 100)
        alert = current_weight < threshold
        name = product['name']

    # JavaScript에서 무게 표시 및 알림 판단용 데이터 반환
    return jsonify({
        'weight': current_weight,
        'threshold': threshold,
        'alert': alert,
        'name': name
    })

# Flask 서버 실행
if __name__ == '__main__':
    os.makedirs('data', exist_ok=True)  # 데이터 폴더 없으면 생성
    app.run(debug=False)
