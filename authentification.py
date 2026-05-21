import os
import bcrypt
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime

DATABASE_URL = os.environ.get('DATABASE_URL')

DEFAULT_ADMIN_USERNAME = os.environ.get('ADMIN_USERNAME', 'admin')
DEFAULT_ADMIN_EMAIL = os.environ.get('ADMIN_EMAIL', 'admin@pharma-saas.com')
DEFAULT_ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'admin123')

def get_db_connection():
    """Create a database connection"""
    try:
        conn = psycopg2.connect(DATABASE_URL)
        return conn
    except Exception as e:
        print(f"Database connection error: {e}")
        return None

def hash_password(password: str) -> str:
    """Hash a password using bcrypt"""
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
    return hashed.decode('utf-8')

def verify_password(password: str, hashed_password: str) -> bool:
    """Verify a password against its hash"""
    return bcrypt.checkpw(password.encode('utf-8'), hashed_password.encode('utf-8'))

def create_user(username: str, email: str, password: str, first_name: str = None, last_name: str = None, role: str = 'user', laboratoire: str = None) -> dict:
    """Create a new user in the database"""
    conn = get_db_connection()
    if not conn:
        return {"success": False, "error": "Erreur de connexion. Veuillez réessayer."}
    
    try:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        cursor.execute("SELECT id FROM users WHERE username = %s OR email = %s", (username, email))
        if cursor.fetchone():
            return {"success": False, "error": "Impossible de créer le compte. Veuillez vérifier vos informations."}
        
        password_hash = hash_password(password)
        
        cursor.execute("""
            INSERT INTO users (username, email, password_hash, first_name, last_name, role, laboratoire)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id, username, email, first_name, last_name, role, laboratoire, created_at
        """, (username, email, password_hash, first_name, last_name, role, laboratoire))
        
        user = cursor.fetchone()
        conn.commit()
        
        return {"success": True, "user": dict(user)}
    
    except Exception as e:
        conn.rollback()
        print(f"User creation error: {e}")
        return {"success": False, "error": "Une erreur s'est produite lors de la création du compte. Veuillez réessayer."}
    
    finally:
        cursor.close()
        conn.close()

def authenticate_user(username_or_email: str, password: str) -> dict:
    """Authenticate a user by username/email and password"""
    conn = get_db_connection()
    if not conn:
        return {"success": False, "error": "Erreur de connexion. Veuillez réessayer."}
    
    try:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        cursor.execute("""
            SELECT id, username, email, password_hash, first_name, last_name, role, is_active, laboratoire
            FROM users 
            WHERE (username = %s OR email = %s) AND is_active = TRUE
        """, (username_or_email, username_or_email))
        
        user = cursor.fetchone()
        
        if not user:
            return {"success": False, "error": "Identifiants incorrects"}
        
        if not verify_password(password, user['password_hash']):
            return {"success": False, "error": "Identifiants incorrects"}
        
        cursor.execute("""
            UPDATE users SET last_login = %s WHERE id = %s
        """, (datetime.now(), user['id']))
        conn.commit()
        
        user_data = dict(user)
        del user_data['password_hash']
        
        return {"success": True, "user": user_data}
    
    except Exception as e:
        print(f"Authentication error: {e}")
        return {"success": False, "error": "Erreur de connexion. Veuillez réessayer."}
    
    finally:
        cursor.close()
        conn.close()

_user_cache = {}
_user_cache_timeout = 60

def get_user_by_id(user_id: int, use_cache: bool = True) -> dict:
    """Get user information by ID with optional caching"""
    if use_cache and user_id in _user_cache:
        cached_time, cached_user = _user_cache[user_id]
        if (datetime.now() - cached_time).seconds < _user_cache_timeout:
            return cached_user
    
    conn = get_db_connection()
    if not conn:
        return None
    
    try:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        cursor.execute("""
            SELECT id, username, email, first_name, last_name, role, is_active, laboratoire, created_at, last_login
            FROM users WHERE id = %s
        """, (user_id,))
        
        user = cursor.fetchone()
        result = dict(user) if user else None
        
        if result and use_cache:
            _user_cache[user_id] = (datetime.now(), result)
        
        return result
    
    except Exception as e:
        return None
    
    finally:
        cursor.close()
        conn.close()

def clear_user_cache(user_id: int = None):
    """Clear user cache - call after user updates"""
    global _user_cache
    if user_id:
        _user_cache.pop(user_id, None)
    else:
        _user_cache = {}

def update_user_password(user_id: int, new_password: str) -> dict:
    """Update user password"""
    conn = get_db_connection()
    if not conn:
        return {"success": False, "error": "Erreur de connexion. Veuillez réessayer."}
    
    try:
        cursor = conn.cursor()
        password_hash = hash_password(new_password)
        
        cursor.execute("""
            UPDATE users SET password_hash = %s WHERE id = %s
        """, (password_hash, user_id))
        
        conn.commit()
        return {"success": True, "message": "Mot de passe mis à jour"}
    
    except Exception as e:
        conn.rollback()
        print(f"Password update error: {e}")
        return {"success": False, "error": "Une erreur s'est produite. Veuillez réessayer."}
    
    finally:
        cursor.close()
        conn.close()

def get_all_users() -> list:
    """Get all users (admin function)"""
    conn = get_db_connection()
    if not conn:
        return []
    
    try:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        cursor.execute("""
            SELECT id, username, email, first_name, last_name, role, is_active, laboratoire, created_at, last_login
            FROM users ORDER BY created_at DESC
        """)
        
        users = cursor.fetchall()
        return [dict(user) for user in users]
    
    except Exception as e:
        return []
    
    finally:
        cursor.close()
        conn.close()

def deactivate_user(user_id: int) -> dict:
    """Deactivate a user account"""
    conn = get_db_connection()
    if not conn:
        return {"success": False, "error": "Erreur de connexion. Veuillez réessayer."}
    
    try:
        cursor = conn.cursor()
        
        cursor.execute("""
            UPDATE users SET is_active = FALSE WHERE id = %s
        """, (user_id,))
        
        conn.commit()
        return {"success": True, "message": "Compte désactivé"}
    
    except Exception as e:
        conn.rollback()
        print(f"Deactivate user error: {e}")
        return {"success": False, "error": "Une erreur s'est produite. Veuillez réessayer."}
    
    finally:
        cursor.close()
        conn.close()

def activate_user(user_id: int) -> dict:
    """Activate a user account"""
    conn = get_db_connection()
    if not conn:
        return {"success": False, "error": "Erreur de connexion. Veuillez réessayer."}
    
    try:
        cursor = conn.cursor()
        
        cursor.execute("""
            UPDATE users SET is_active = TRUE WHERE id = %s
        """, (user_id,))
        
        conn.commit()
        return {"success": True, "message": "Compte activé"}
    
    except Exception as e:
        conn.rollback()
        print(f"Activate user error: {e}")
        return {"success": False, "error": "Une erreur s'est produite. Veuillez réessayer."}
    
    finally:
        cursor.close()
        conn.close()

def delete_user(user_id: int, current_user_id: int = None) -> dict:
    """Permanently delete a user account"""
    if current_user_id and user_id == current_user_id:
        return {"success": False, "error": "Vous ne pouvez pas supprimer votre propre compte."}

    conn = get_db_connection()
    if not conn:
        return {"success": False, "error": "Erreur de connexion. Veuillez réessayer."}
    
    try:
        cursor = conn.cursor()
        
        cursor.execute("DELETE FROM users WHERE id = %s", (user_id,))
        
        conn.commit()
        return {"success": True, "message": "Compte supprimé"}
    
    except Exception as e:
        conn.rollback()
        print(f"Delete user error: {e}")
        return {"success": False, "error": "Une erreur s'est produite. Veuillez réessayer."}
    
    finally:
        cursor.close()
        conn.close()

def update_user_laboratoire(user_id: int, laboratoire: str) -> dict:
    """Update user laboratoire"""
    conn = get_db_connection()
    if not conn:
        return {"success": False, "error": "Erreur de connexion. Veuillez réessayer."}
    
    try:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE users SET laboratoire = %s WHERE id = %s
        """, (laboratoire if laboratoire else None, user_id))
        conn.commit()
        return {"success": True, "message": "Laboratoire mis à jour"}
    except Exception as e:
        conn.rollback()
        print(f"Update laboratoire error: {e}")
        return {"success": False, "error": "Une erreur s'est produite. Veuillez réessayer."}
    finally:
        cursor.close()
        conn.close()

def update_user_role(user_id: int, new_role: str) -> dict:
    """Update user role"""
    valid_roles = ['user', 'admin', 'manager']
    if new_role not in valid_roles:
        return {"success": False, "error": "Rôle invalide."}
    
    conn = get_db_connection()
    if not conn:
        return {"success": False, "error": "Erreur de connexion. Veuillez réessayer."}
    
    try:
        cursor = conn.cursor()
        
        cursor.execute("""
            UPDATE users SET role = %s WHERE id = %s
        """, (new_role, user_id))
        
        conn.commit()
        return {"success": True, "message": "Rôle mis à jour"}
    
    except Exception as e:
        conn.rollback()
        print(f"Update role error: {e}")
        return {"success": False, "error": "Une erreur s'est produite. Veuillez réessayer."}
    
    finally:
        cursor.close()
        conn.close()

def init_distance_table():
    """Create and populate distance_secteurs table if it doesn't exist"""
    conn = get_db_connection()
    if not conn:
        return False
    try:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS distance_secteurs (
                id SERIAL PRIMARY KEY,
                secteur_from VARCHAR(50) NOT NULL,
                secteur_to VARCHAR(50) NOT NULL,
                distance DOUBLE PRECISION NOT NULL,
                UNIQUE(secteur_from, secteur_to)
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_distance_secteurs_from ON distance_secteurs(secteur_from)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_distance_secteurs_to ON distance_secteurs(secteur_to)")
        cursor.execute("SELECT COUNT(*) FROM distance_secteurs")
        count = cursor.fetchone()[0]
        if count == 0:
            import json
            data_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'distance_secteurs_data.json')
            if os.path.exists(data_file):
                with open(data_file, 'r') as f:
                    pairs = json.load(f)
                batch_size = 500
                for i in range(0, len(pairs), batch_size):
                    batch = pairs[i:i+batch_size]
                    values_str = ','.join(
                        cursor.mogrify("(%s,%s,%s)", (p[0], p[1], p[2])).decode()
                        for p in batch
                    )
                    cursor.execute(f"INSERT INTO distance_secteurs (secteur_from, secteur_to, distance) VALUES {values_str} ON CONFLICT (secteur_from, secteur_to) DO NOTHING")
                print(f"Distance table populated with {len(pairs)} entries")
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        print(f"Distance table init error: {e}")
        return False
    finally:
        cursor.close()
        conn.close()

def init_admin_user():
    """Create default admin user if it doesn't exist"""
    conn = get_db_connection()
    if not conn:
        print("Cannot initialize admin user: database connection failed")
        return False
    
    try:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        cursor.execute("SELECT id FROM users WHERE username = %s OR email = %s", 
                      (DEFAULT_ADMIN_USERNAME, DEFAULT_ADMIN_EMAIL))
        if cursor.fetchone():
            return True
        
        password_hash = hash_password(DEFAULT_ADMIN_PASSWORD)
        
        cursor.execute("""
            INSERT INTO users (username, email, password_hash, first_name, last_name, role)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (DEFAULT_ADMIN_USERNAME, DEFAULT_ADMIN_EMAIL, password_hash, "Admin", "System", "admin"))
        
        conn.commit()
        print("Default admin user created successfully")
        return True
    
    except Exception as e:
        conn.rollback()
        print(f"Admin initialization error: {e}")
        return False
    
    finally:
        cursor.close()
        conn.close()
