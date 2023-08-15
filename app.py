
from flask import Flask, render_template, request, redirect, url_for, session
from flask_paginate import Pagination, get_page_args
from sqlalchemy import create_engine, Column, Integer, String, TIMESTAMP
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime, timedelta
from sqlalchemy.sql import exists
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


                message_id = request.form['message_id']
                instruction_vi = request.form['instruction_vi']
                input_vi = request.form['input_vi']
                output_vi = request.form['output_vi']

                update_instruction_data(message_id, instruction_vi, input_vi, output_vi)
                saved = True
            except Exception as e:
                saved = False
                # Handle the error, you might want to log it or show a user-friendly message
                print("Error while updating data:", e)

    data, data_vi = get_random()
    return render_template('main.html', logged_in=session.get('logged_in'), phone_number=session.get('phone_number'),
                           data=data, data_vi=data_vi, saved=saved)


def update_instruction_data(message_id, instruction_vi, input_vi, output_vi):
    db_session = Session()
    try:
        db_session.query(InstructionDataset).filter_by(message_id=message_id,  lang='vi').update({
            'instruction': instruction_vi,
            'input': input_vi,
            'output': output_vi
        })
        db_session.commit()
    except Exception as e:
        db_session.rollback()
        raise e
    finally:
        db_session.close()


def update_data_status(message_id, new_status, phone_number):
    db_session = Session()
    try:
        utc_now = datetime.utcnow()
        utc_offset = timedelta(hours=7)
        local_time = utc_now + utc_offset

        db_session.query(LogInstructionDataset).filter_by(message_id=message_id).update({
            'status': new_status,
            'modified_date': local_time,
            'phone_number': phone_number,
        })

        db_session.commit()
    except Exception as e:
        db_session.rollback()
        print("Error while updating status:", e)  # In ra thông tin lỗi
    finally:
        db_session.close()



def create_log_data(message_id, phone_number, status):
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
            # Tạo subquery để lấy các message_id đã submitted
            submitted_message_subquery = db_session.query(LogInstructionDataset.message_id).filter(LogInstructionDataset.status.like('%submitted%')).subquery()
            
            # Lấy dữ liệu ngẫu nhiên không trùng với các message_id đã submitted
            random_data = db_session.query(InstructionDataset)\
                .filter(~InstructionDataset.message_id.in_(submitted_message_subquery))\
                .order_by(func.random())\
                .first()

            if random_data:
                create_log_data(random_data.message_id, session.get('phone_number'), 'repairing')
                
                # Lấy các bản ghi có cùng message_id
                data_list = db_session.query(InstructionDataset)\
                    .filter_by(message_id=random_data.message_id)\
                    .limit(2)\
                    .all()

        #Câu lệnh kiểm tra nếu data_list có 2 phần tử
        if data_list and len(data_list) == 2:
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
        # Trường hợp data_en rỗng
        else:
            data_vi = data_list[0]
            data = {
                    'message_id': data_list[0].message_id,
                    'instruction': '',
                    'input': '',
                    'output': '',
            }                      
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

@app.route('/log', methods=['GET', 'POST'])
def log():
    db_session = Session()
    try:
        search_query = request.args.get('search', '')  # Lấy giá trị tìm kiếm từ query string

        # Get page and per_page from query string or use default values
        page, per_page, offset = get_page_args(page_parameter='page', per_page_parameter='per_page')

        # Tìm kiếm trong bảng LogInstructionDataset và chỉ hiển thị các dòng với message_id chứa search_query
        log_data = db_session.query(LogInstructionDataset).filter(LogInstructionDataset.message_id.like(f'%{search_query}%'),  LogInstructionDataset.status == 'submitted', LogInstructionDataset.phone_number==session.get('phone_number')).order_by(LogInstructionDataset.modified_date.desc()).offset(offset).limit(per_page).all()

        total = db_session.query(LogInstructionDataset).filter(LogInstructionDataset.message_id.like(f'%{search_query}%')).count()

        instruction_data = []  # Danh sách chứa thông tin từ instruction_dataset
        for data in log_data:
            query_result = db_session.query(InstructionDataset.lang, InstructionDataset.instruction, InstructionDataset.input, InstructionDataset.output).filter_by(message_id=data.message_id).all()

            instruction_en = {}
            instruction_vi = {}

            for query_item in query_result:
                if query_item.lang == 'en':
                    instruction_en = {
                        'instruction_en': query_item.instruction,
                        'input_en': query_item.input,
                        'output_en': query_item.output,
                    }
                else:
                    instruction_vi = {
                        'instruction_vi': query_item.instruction,
                        'input_vi': query_item.input,
                        'output_vi': query_item.output,
                    }

            # Gộp dữ liệu từ cả hai ngôn ngữ vào một dict
            instruction_combined = {
                **instruction_en,
                **instruction_vi
            }

            instruction_data.append(instruction_combined)

        log_data_instruction = zip(log_data, instruction_data)  # Gộp dữ liệu log_data và instruction_data

        # Create a Pagination object
        pagination = Pagination(page=page, per_page=per_page, total=total, css_framework='bootstrap4')
    finally:
        db_session.close()

    return render_template('log.html', log_data_instruction=log_data_instruction, pagination=pagination, search_query=search_query)

@app.route('/update/<message_id>', methods=['POST'])
def save_data(message_id):
    try:
        if request.method == 'POST':
            instruction_vi = request.form.get('instruction_vi')
            input_vi = request.form.get('input_vi')
            output_vi = request.form.get('output_vi')

            # Cập nhật dữ liệu trong bảng instruction_dataset
            update_instruction_data(message_id, instruction_vi, input_vi, output_vi)

            # Cập nhật trạng thái và thời gian sửa đổi trong bảng log_instruction_dataset
            update_data_status(message_id, 'submitted', session.get('phone_number'))

            return "success"  # Trả về thông báo thành công
        else:
            return "error"  # Trả về thông báo lỗi nếu request.method không phải là POST
    except Exception as e:
        print("Error while saving data:", e)
        return "error"  # Trả về thông báo lỗi nếu có lỗi xảy ra
    
@app.route('/delete/<message_id>', methods=['POST'])
def delete_data(message_id):
    try:
        db_session = Session()
        # Delete data from log_instruction_dataset 
        db_session.query(LogInstructionDataset).filter_by(message_id=message_id).delete()
        db_session.commit()
        return "success"  # Return success message if deletion is successful
    except Exception as e:
        print("Error while deleting data:", e)
        return "error"  # Return error message if there's an error during deletion
    finally:
        db_session.close()


if __name__ == '__main__':
    app.run(debug=True, host='192.168.1.15', port=5000)