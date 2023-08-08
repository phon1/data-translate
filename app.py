from flask import Flask, render_template, request, redirect, url_for, session
from sqlalchemy import create_engine, Column, Integer, String, TIMESTAMP
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime, timedelta
from sqlalchemy import func  

import random

app = Flask(__name__)
app.secret_key = 'your_secret_key_here'

# Cấu hình PostgreSQL database
db_user = 'kami'
db_password = '123'
db_host = '192.168.1.200'
db_port = '5432'
db_name = 'phongdev'

# Kết nối đến cơ sở dữ liệu PostgreSQL
engine = create_engine(f'postgresql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}')
Base = declarative_base()
Session = sessionmaker(bind=engine)


class InstructionDataset(Base):
    __tablename__ = 'instruction_dataset'
    id = Column(Integer, primary_key=True)
    dataset = Column(String)
    lang = Column(String)
    message_id = Column(String)
    data_id = Column(String)
    instruction = Column(String)
    input = Column(String)
    output = Column(String)


class LogInstructionDataset(Base):
    __tablename__ = 'log_instruction_dataset'
    id = Column(Integer, primary_key=True)
    message_id = Column(String)
    modified_date = Column(TIMESTAMP)
    phone_number = Column(String)
    status = Column(String)


@app.route('/')
def index():
    return redirect(url_for('login'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        phone_number = request.form.get('phoneNumber')

        # Kiểm tra nếu số điện thoại chứa ký tự không phải số
        if not phone_number.isdigit():
            error = 'Phải nhập số điện thoại bằng các ký tự số'
            return render_template('login.html', error=error)

        # Kiểm tra nếu độ dài số điện thoại không nằm trong khoảng từ 6-15 ký tự
        if not 6 <= len(phone_number) <= 15:
            error = 'Phải nhập từ 6-15 ký tự số'
            return render_template('login.html', error=error)

        # Nếu số điện thoại hợp lệ, chuyển hướng sang trang main và lưu số điện thoại vào session
        session['logged_in'] = True
        session['phone_number'] = phone_number
        return redirect(url_for('main'))

    return render_template('login.html', error=None)

@app.route('/main', methods=['GET', 'POST'])
def main():
    if not session.get('logged_in'):
        return redirect(url_for('login'))

    saved = False

    if request.method == 'POST':
        if 'save_button' in request.form and 'message_id' in request.form:
            try:
                # Attempt to update the status, modified date, and phone number of the data in the log
                update_data_status(request.form['message_id'], 'submitted', session.get('phone_number'))
                saved = True
            except Exception as e:
                saved = False
                # Handle the error, you might want to log it or show a user-friendly message
                print("Error while updating data:", e)

        session.pop('logged_in', None)
        session.pop('phone_number', None)
        return redirect(url_for('login'))

    data, data_vi = get_random()
    return render_template('main.html', logged_in=session.get('logged_in'), phone_number=session.get('phone_number'),
                           data=data, data_vi=data_vi, saved=saved)

def update_data_status(message_id, new_status, phone_number):
    db_session = Session()
    try:
        utc_now = datetime.utcnow()
        utc_offset = timedelta(hours=7)
        local_time = utc_now + utc_offset

        db_session.query(LogInstructionDataset).filter_by(message_id=message_id).update({
            'status': new_status,
            'modified_date': local_time,
            'phone_number': phone_number
        })

        db_session.commit()
    except Exception as e:
        db_session.rollback()
        raise e
    finally:
        db_session.close()


def save_data_to_log(message_id, phone_number, status):
    db_session = Session()
    try:
        utc_now = datetime.utcnow()
        utc_offset = timedelta(hours=7)
        local_time = utc_now + utc_offset

        new_entry = LogInstructionDataset(
            message_id=message_id,
            modified_date=local_time,
            phone_number=phone_number,
            status=status
        )
        db_session.add(new_entry)
        db_session.commit()
    except Exception as e:
        db_session.rollback()  # Rollback the transaction in case of an error
        raise e
    finally:
        db_session.close()

def get_random():
    db_session = Session()
    try:
        # Lấy thông tin từ bảng log_instruction_dataset
        repairing_entry = db_session.query(LogInstructionDataset).filter_by(status='repairing', phone_number=session.get('phone_number')).first()
        if repairing_entry:
            data_list = db_session.query(InstructionDataset).filter_by(message_id=repairing_entry.message_id).all()
        else:
            # Nếu trạng thái không phải "repairing", tìm dữ liệu ngẫu nhiên với điều kiện message_id không trùng với status "submitted"
            table_submit = db_session.query(LogInstructionDataset.message_id).filter(LogInstructionDataset.status.like('%submitted%')).all()
            submitted_message_ids = [item[0] for item in table_submit]

            # Lấy dữ liệu ngẫu nhiên không trùng với submitted_message_ids
            random_data = db_session.query(InstructionDataset).filter(InstructionDataset.message_id.notin_(submitted_message_ids)).order_by(func.random()).first()

            # Nếu có dữ liệu ngẫu nhiên, lấy thêm một dòng khác có cùng message_id
            if random_data:
                save_data_to_log(random_data.message_id, session.get('phone_number'), 'repairing')
                data_list = db_session.query(InstructionDataset).filter_by(message_id=random_data.message_id).limit(2).all()


        if data_list[0].lang == 'en':
            data = data_list[0]
            data_vi = data_list[1]
        else:
            data = data_list[1]
            data_vi = data_list[0]

        if data:
            data = {
                'message_id': data.message_id,
                'instruction': data.instruction,
                'input': data.input,
                'output': data.output,
            }
        if data_vi:
            data_vi = {
                'id': data_vi.id,
                'message_id': data_vi.message_id,
                'instruction_vi': data_vi.instruction,
                'input_vi': data_vi.input,
                'output_vi': data_vi.output,
            }
    finally:
        db_session.close()

    return data, data_vi


@app.route('/log')
def log():
    db_session = Session()
    try:
        log_data = db_session.query(LogInstructionDataset).all()
    finally:
        db_session.close()

    return render_template('log.html', log_data=log_data)


if __name__ == '__main__':
    app.run(debug=True)