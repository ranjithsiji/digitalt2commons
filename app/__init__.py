from flask import Flask
import os

def create_app():
    app = Flask(__name__, template_folder='templates')  # Explicitly set template folder
    app.config.from_object('config.Config')
    
    # Ensure templates folder exists
    if not os.path.exists(os.path.join(app.root_path, 'templates')):
        os.makedirs(os.path.join(app.root_path, 'templates'))
    
    from app.main import bp as main_bp
    app.register_blueprint(main_bp)
    
    return app