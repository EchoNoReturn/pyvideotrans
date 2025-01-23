from flask import Flask, Blueprint, jsonify

# 创建蓝图
app = Flask(__name__)
api_bp = Blueprint('api', __name__, url_prefix='/api')

# Hello World
@api_bp.route('/hello', methods=['GET'])
def hello():
    return jsonify({"message": "Hello, World!"})


# 服务启动
app.register_blueprint(api_bp)
if __name__ == '__main__':
    app.run(host='127.0.0.1', port=8080)