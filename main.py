import pygame
import random
import math
import os
import time
import json
import pickle
import zipfile
import shutil
from xml.dom import minidom
import sys

# Папка для данных, которые должны переживать обновление игры (миры, моды,
# конфиг модов). На ПК - рядом с игрой; на Android (python-for-android) -
# приватная папка приложения: папка с самой игрой там перезаписывается при
# каждом обновлении APK, и миры бы пропадали.
DATA_DIR = os.environ.get('ANDROID_PRIVATE') or '.'

# На Android ресурсы (Textures, Music) лежат в папке приложения
# (ANDROID_ARGUMENT). Относительные пути вида "Textures/..." работают только
# если рабочая папка = папка с игрой, поэтому переходим в неё явно.
_android_app_dir = os.environ.get('ANDROID_ARGUMENT')
if _android_app_dir and os.path.isdir(_android_app_dir):
    try:
        os.chdir(_android_app_dir)
    except Exception:
        pass


def _count_files(path):
    """Сколько файлов в папке (рекурсивно); -1 если папки нет."""
    if not os.path.isdir(path):
        return -1
    total = 0
    for _root, _dirs, files in os.walk(path):
        total += len(files)
    return total

# --- КОНСТАНТЫ ---
pygame.init()
info = pygame.display.Info()
WIDTH, HEIGHT = info.current_w, info.current_h
TILE_SIZE = 40
FPS = 60
MAX_LIQUID_LEVEL = 7 

# Событие: трек фоновой музыки закончился (для рандомного плейлиста)
MUSIC_END_EVENT = pygame.USEREVENT + 1

# Оптимизация: размер чанка для генерации
CHUNK_SIZE = 16
RENDER_DISTANCE = 10  # Уменьшено для оптимизации
UPDATE_DISTANCE = 12

# ID Блоков и предметов
EMPTY, GRASS, DIRT, STONE, WATER, LAVA, WOOD, LEAVES, SAND, PLANK = 0, 1, 2, 3, 4, 5, 6, 7, 8, 9
SNOW_GRASS, ASH, CACTUS, PINE_LEAVES, PINE_LOG = 10, 11, 12, 13, 14
STICK, CRAFTING_TABLE, WOODEN_PICKAXE, WOODEN_AXE, WOODEN_SWORD = 15, 16, 17, 18, 19
STONE_PICKAXE, STONE_AXE, STONE_SWORD = 20, 21, 22
GLASS, WOODEN_DOOR, IRON_DOOR = 23, 24, 25  # IRON_DOOR удалена из игры (ID зарезервирован)
FURNACE, COAL_ORE, IRON_ORE, GOLD_ORE, DIAMOND_ORE = 26, 27, 28, 29, 30  # DIAMOND_ORE удалён из игры (ID зарезервирован)
COAL, IRON_INGOT, GOLD_INGOT, DIAMOND = 31, 32, 33, 34  # DIAMOND удалён из игры (ID зарезервирован)
IRON_PICKAXE, IRON_AXE, IRON_SWORD = 35, 36, 37
GOLD_PICKAXE, GOLD_AXE, GOLD_SWORD = 38, 39, 40
DIAMOND_PICKAXE, DIAMOND_AXE, DIAMOND_SWORD = 41, 42, 43  # удалены из игры (ID зарезервированы)
STONE_BRICK, IRON_BLOCK, GOLD_BLOCK, DIAMOND_BLOCK = 44, 45, 46, 47  # DIAMOND_BLOCK удалён из игры (ID зарезервирован)
CHEST, TORCH = 48, 49
PINE_WOOD, PINE_DOOR = 50, 51
PINE_PLANK = 52

# --- КЛАССЫ ---
class Chunk:
    """Класс для управления чанками - оптимизация"""
    def __init__(self, cx, cy):
        self.cx = cx
        self.cy = cy
        self.blocks = {}  # (x, y) -> block_data
        self.generated = False
        self.decor_generated = False
        self.ores_generated = False
        self.last_accessed = time.time()
    
    def get_block(self, x, y):
        self.last_accessed = time.time()
        return self.blocks.get((x, y))
    
    def set_block(self, x, y, block_data):
        self.last_accessed = time.time()
        self.blocks[(x, y)] = block_data

class ModManager:
    def __init__(self, game):
        self.game = game
        self.mods_dir = os.path.join(DATA_DIR, "mods")
        self.active_mods = []
        self.available_mods = []
        self.mod_metadata = {}
        
        try:
            if not os.path.exists(self.mods_dir):
                os.makedirs(self.mods_dir)
        except Exception as e:
            print(f"Ошибка создания папки модов: {e}")
        
        self.load_mod_config()
        self.scan_mods()
    
    def scan_mods(self):
        """Сканирует папку с модами"""
        self.available_mods = []
        self.mod_metadata = {}
        
        try:
            if not os.path.exists(self.mods_dir):
                os.makedirs(self.mods_dir)
                return
            
            items = os.listdir(self.mods_dir)
        except Exception as e:
            print(f"Ошибка доступа к папке модов: {e}")
            return
        
        for item in items:
            try:
                mod_path = os.path.join(self.mods_dir, item)
                
                if os.path.isdir(mod_path) or (os.path.isfile(mod_path) and (item.endswith('.zip') or item.endswith('.modpack'))):
                    mod_id = os.path.splitext(item)[0]
                    
                    metadata = self.load_mod_metadata(mod_path)
                    if metadata:
                        self.mod_metadata[mod_id] = metadata
                    
                    self.available_mods.append({
                        'id': mod_id,
                        'path': mod_path,
                        'name': metadata.get('name', mod_id) if metadata else mod_id,
                        'version': metadata.get('version', '0.9') if metadata else '0.9',
                        'author': metadata.get('author', 'Unknown') if metadata else 'Unknown',
                        'description': metadata.get('description', '') if metadata else '',
                        'enabled': mod_id in self.active_mods
                    })
            except Exception as e:
                print(f"Ошибка обработки мода {item}: {e}")
                continue
    
    def load_mod_metadata(self, mod_path):
        """Загружает метаданные мода"""
        metadata = {}
        
        try:
            if mod_path.endswith('.zip') or mod_path.endswith('.modpack'):
                if not os.path.exists(mod_path):
                    return metadata
                    
                with zipfile.ZipFile(mod_path, 'r') as zip_ref:
                    if 'mod.xml' in zip_ref.namelist():
                        with zip_ref.open('mod.xml') as xml_file:
                            xml_content = xml_file.read().decode('utf-8', errors='ignore')
                            from io import StringIO
                            dom = minidom.parseString(xml_content)
                            root = dom.documentElement
                            
                            if root.tagName == 'mod':
                                metadata['id'] = root.getAttribute('id')
                                metadata['name'] = root.getAttribute('name')
                                metadata['version'] = root.getAttribute('version')
                                metadata['author'] = root.getAttribute('author')
                                
                                desc_elem = root.getElementsByTagName('description')
                                if desc_elem and desc_elem[0].firstChild:
                                    metadata['description'] = desc_elem[0].firstChild.nodeValue
            elif os.path.isdir(mod_path):
                xml_path = os.path.join(mod_path, 'mod.xml')
                if os.path.exists(xml_path):
                    with open(xml_path, 'r', encoding='utf-8', errors='ignore') as f:
                        dom = minidom.parse(f)
                        root = dom.documentElement
                        
                        if root.tagName == 'mod':
                            metadata['id'] = root.getAttribute('id')
                            metadata['name'] = root.getAttribute('name')
                            metadata['version'] = root.getAttribute('version')
                            metadata['author'] = root.getAttribute('author')
                            
                            desc_elem = root.getElementsByTagName('description')
                            if desc_elem and desc_elem[0].firstChild:
                                metadata['description'] = desc_elem[0].firstChild.nodeValue
        except Exception as e:
            print(f"Ошибка загрузки метаданных мода {mod_path}: {e}")
        
        return metadata
    
    def load_mod_config(self):
        """Загружает конфигурацию модов"""
        config_path = os.path.join(DATA_DIR, 'mods_config.json')
        if os.path.exists(config_path):
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    self.active_mods = config.get('active_mods', [])
            except:
                self.active_mods = []
        else:
            self.active_mods = []
    
    def save_mod_config(self):
        """Сохраняет конфигурацию модов"""
        config_path = os.path.join(DATA_DIR, 'mods_config.json')
        config = {
            'active_mods': self.active_mods
        }
        
        try:
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"Ошибка сохранения конфигурации модов: {e}")
    
    def enable_mod(self, mod_id):
        """Включает мод"""
        if mod_id not in self.active_mods:
            self.active_mods.append(mod_id)
            self.save_mod_config()
            return True
        return False
    
    def disable_mod(self, mod_id):
        """Выключает мод"""
        if mod_id in self.active_mods:
            self.active_mods.remove(mod_id)
            self.save_mod_config()
            return True
        return False
    
    def get_mod_textures(self, mod_id):
        """Получает текстуры из мода"""
        textures = {}
        mod_info = None
        
        for mod in self.available_mods:
            if mod['id'] == mod_id:
                mod_info = mod
                break
        
        if not mod_info:
            return textures
        
        mod_path = mod_info['path']
        
        try:
            if not os.path.exists(mod_path):
                return textures
                
            if mod_path.endswith('.zip') or mod_path.endswith('.modpack'):
                with zipfile.ZipFile(mod_path, 'r') as zip_ref:
                    for file_info in zip_ref.infolist():
                        if file_info.filename.startswith('textures/') and file_info.filename.endswith('.png'):
                            filename = os.path.basename(file_info.filename)
                            texture_name = os.path.splitext(filename)[0]
                            
                            texture_id = self.get_texture_id_by_name(texture_name)
                            if texture_id is not None:
                                try:
                                    with zip_ref.open(file_info.filename) as img_file:
                                        img_data = img_file.read()
                                        temp_path = f"temp_{texture_name}_{random.randint(1000,9999)}.png"
                                        with open(temp_path, 'wb') as temp_file:
                                            temp_file.write(img_data)
                                        
                                        try:
                                            img = pygame.image.load(temp_path).convert_alpha()
                                            textures[texture_id] = pygame.transform.scale(img, (TILE_SIZE, TILE_SIZE))
                                        except Exception as e:
                                            print(f"Ошибка загрузки текстуры {texture_name}: {e}")
                                        finally:
                                            if os.path.exists(temp_path):
                                                try:
                                                    os.remove(temp_path)
                                                except:
                                                    pass
                                except Exception as e:
                                    print(f"Ошибка чтения текстуры из zip: {e}")
            
            elif os.path.isdir(mod_path):
                textures_dir = os.path.join(mod_path, 'textures')
                if os.path.exists(textures_dir):
                    for filename in os.listdir(textures_dir):
                        if filename.endswith('.png'):
                            texture_name = os.path.splitext(filename)[0]
                            texture_id = self.get_texture_id_by_name(texture_name)
                            
                            if texture_id is not None:
                                img_path = os.path.join(textures_dir, filename)
                                try:
                                    img = pygame.image.load(img_path).convert_alpha()
                                    textures[texture_id] = pygame.transform.scale(img, (TILE_SIZE, TILE_SIZE))
                                except Exception as e:
                                    print(f"Ошибка загрузки текстуры {filename}: {e}")
        except Exception as e:
            print(f"Ошибка загрузки текстур из мода {mod_id}: {e}")
        
        return textures
    
    def get_texture_id_by_name(self, texture_name):
        """Преобразует имя текстуры в ID"""
        texture_map = {
            'grass': GRASS,
            'dirt': DIRT,
            'stone': STONE,
            'water': WATER,
            'lava': LAVA,
            'wood': WOOD,
            'leaves': LEAVES,
            'sand': SAND,
            'plank': PLANK,
            'snow': SNOW_GRASS,
            'ash': ASH,
            'cactus': CACTUS,
            'pine_leaves': PINE_LEAVES,
            'pine_log': PINE_LOG,
            'stick': STICK,
            'crafting_table': CRAFTING_TABLE,
            'wooden_pickaxe': WOODEN_PICKAXE,
            'wooden_axe': WOODEN_AXE,
            'wooden_sword': WOODEN_SWORD,
            'stone_pickaxe': STONE_PICKAXE,
            'stone_axe': STONE_AXE,
            'stone_sword': STONE_SWORD,
            'glass': GLASS,
            'wooden_door_closed': WOODEN_DOOR,
            'wooden_door_open': WOODEN_DOOR,  # Используем тот же ID, но с отдельной текстурой
            'iron_door_closed': IRON_DOOR,
            'iron_door_open': IRON_DOOR,      # Используем тот же ID, но с отдельной текстурой
            'furnace': FURNACE,
            'coal_ore': COAL_ORE,
            'iron_ore': IRON_ORE,
            'gold_ore': GOLD_ORE,
            'diamond_ore': DIAMOND_ORE,
            'coal': COAL,
            'iron_ingot': IRON_INGOT,
            'gold_ingot': GOLD_INGOT,
            'diamond': DIAMOND,
            'iron_pickaxe': IRON_PICKAXE,
            'iron_axe': IRON_AXE,
            'iron_sword': IRON_SWORD,
            'gold_pickaxe': GOLD_PICKAXE,
            'gold_axe': GOLD_AXE,
            'gold_sword': GOLD_SWORD,
            'diamond_pickaxe': DIAMOND_PICKAXE,
            'diamond_axe': DIAMOND_AXE,
            'diamond_sword': DIAMOND_SWORD,
            'stone_brick': STONE_BRICK,
            'iron_block': IRON_BLOCK,
            'gold_block': GOLD_BLOCK,
            'diamond_block': DIAMOND_BLOCK,
            'torch': TORCH,
            'pine_wood': PINE_WOOD,
            'pine_door_closed': PINE_DOOR,
            'pine_door_open': PINE_DOOR,      # Используем тот же ID, но с отдельной текстурой
            'pine_plank': PINE_PLANK,
        }
        
        return texture_map.get(texture_name.lower())
    
    def apply_mod_textures(self, game_textures):
        """Применяет текстуры из модов"""
        if not self.active_mods:
            return game_textures
            
        for mod_id in self.active_mods:
            try:
                mod_textures = self.get_mod_textures(mod_id)
                for texture_id, texture in mod_textures.items():
                    if texture_id in game_textures:
                        game_textures[texture_id] = texture
            except Exception as e:
                print(f"Ошибка применения текстур мода {mod_id}: {e}")
        
        return game_textures

class Torch:
    def __init__(self, x, y):
        self.x = x
        self.y = y
        self.light_level = 10
        self.flicker_timer = 0
        self.flicker_offset = random.uniform(0, 2*math.pi)
        self.current_light = self.light_level
    
    def update(self):
        self.flicker_timer += 0.1
        self.current_light = self.light_level + math.sin(self.flicker_timer + self.flicker_offset) * 0.5

class DroppedItem:
    _icon_cache = {}  # Общий кэш масштабированных иконок 20x20 по item_id

    def __init__(self, item_id, x, y, count=1):
        self.item_id = item_id
        self.x = x
        self.y = y
        self.width = 20
        self.height = 20
        self.vel_x = random.uniform(-2, 2)
        self.vel_y = random.uniform(-3, -1)
        self.lifetime = 300
        self.created_time = time.time()
        self.on_ground = False
        self.count = count
        self.gravity = 0.3
        self.friction = 0.8
        
    def update(self, world):
        if time.time() - self.created_time > self.lifetime:
            return False
        
        if not self.on_ground:
            self.vel_y += self.gravity
            if self.vel_y > 8:
                self.vel_y = 8
                
            new_x = self.x + self.vel_x
            new_y = self.y + self.vel_y
            
            hit_ground = False
            item_rect = pygame.Rect(new_x, new_y, self.width, self.height)
            
            min_x = int(new_x // TILE_SIZE) - 1
            max_x = int((new_x + self.width) // TILE_SIZE) + 1
            min_y = int(new_y // TILE_SIZE) - 1
            max_y = int((new_y + self.height) // TILE_SIZE) + 1
            
            for check_x in range(min_x, max_x + 1):
                for check_y in range(min_y, max_y + 1):
                    if (check_x, check_y) in world:
                        block_id = world[(check_x, check_y)][0]
                        if block_id not in [EMPTY, WATER, LAVA, LEAVES, PINE_LEAVES, GLASS, TORCH, WOOD, PINE_WOOD, CACTUS]:
                            block_rect = pygame.Rect(check_x * TILE_SIZE, check_y * TILE_SIZE, TILE_SIZE, TILE_SIZE)
                            if item_rect.colliderect(block_rect):
                                if self.vel_y > 0:
                                    self.y = block_rect.top - self.height
                                    self.on_ground = True
                                    self.vel_y = 0
                                    hit_ground = True
                                    break
                                elif self.vel_y < 0:
                                    self.y = block_rect.bottom
                                    self.vel_y = 0
                                    hit_ground = True
                                    break
                                elif self.vel_x > 0:
                                    self.x = block_rect.left - self.width
                                    self.vel_x = 0
                                elif self.vel_x < 0:
                                    self.x = block_rect.right
                                    self.vel_x = 0
                    
                    if hit_ground:
                        break
                if hit_ground:
                    break
            
            if not hit_ground:
                self.x = new_x
                self.y = new_y
            else:
                self.x += self.vel_x
            
            self.vel_x *= 0.95
            
        else:
            self.vel_x *= self.friction
            if abs(self.vel_x) < 0.1:
                self.vel_x = 0
            self.x += self.vel_x
            
            below_rect = pygame.Rect(self.x, self.y + self.height + 1, self.width, 1)
            below_empty = True
            
            min_x = int(self.x // TILE_SIZE)
            max_x = int((self.x + self.width) // TILE_SIZE)
            below_y = int((self.y + self.height + 1) // TILE_SIZE)
            
            for check_x in range(min_x, max_x + 1):
                if (check_x, below_y) in world:
                    block_id = world[(check_x, below_y)][0]
                    if block_id not in [EMPTY, WATER, LAVA, LEAVES, PINE_LEAVES, GLASS, TORCH, WOOD, PINE_WOOD, CACTUS]:
                        below_empty = False
                        break
            
            if below_empty:
                self.on_ground = False
        
        return True
    
    def get_rect(self):
        return pygame.Rect(self.x, self.y, self.width, self.height)
    
    def draw(self, screen, textures, camera_x, camera_y):
        if self.item_id in textures:
            rx = self.x - camera_x
            ry = self.y - camera_y
            if -self.width <= rx <= WIDTH and -self.height <= ry <= HEIGHT:
                # Кэшируем масштабированную иконку по item_id прямо на
                # словаре textures (через отдельный атрибут класса) - размер
                # выпавших предметов всегда фиксирован (20x20), так что без
                # кэша это было ненужное pygame.transform.scale на каждый
                # предмет на земле каждый кадр.
                cache = DroppedItem._icon_cache
                icon = cache.get(self.item_id)
                if icon is None:
                    icon = pygame.transform.scale(textures[self.item_id], (self.width, self.height))
                    cache[self.item_id] = icon
                screen.blit(icon, (rx, ry))
                
                if self.count > 1:
                    try:
                        font = pygame.font.SysFont("Arial", 12, bold=True)
                        count_text = font.render(str(self.count), True, (255, 255, 255))
                        screen.blit(count_text, (rx + 10, ry + 10))
                    except:
                        pass

class Furnace:
    def __init__(self, x, y):
        self.x = x
        self.y = y
        self.input_item = None
        self.input_count = 0
        self.fuel_item = None
        self.fuel_count = 0
        self.output_item = None
        self.output_count = 0
        self.is_burning = False
        self.burn_time = 0
        self.max_burn_time = 0
        self.progress = 0
        self.max_progress = 6.0
        
        self.recipes = {
            IRON_ORE: (IRON_INGOT, 1),
            GOLD_ORE: (GOLD_INGOT, 1),
            COAL_ORE: (COAL, 1),
            WOOD: (COAL, 1),
            PINE_LOG: (COAL, 1),
            STONE: (STONE_BRICK, 1),
        }
        
        self.fuel_times = {
            COAL: 10,
            WOOD: 6,
            PLANK: 3,
            PINE_LOG: 6,
            PINE_PLANK: 3,
            STICK: 2,
        }
    
    def update(self):
        if self.is_burning and self.burn_time > 0:
            self.burn_time -= 0.05
            if self.burn_time <= 0:
                self.is_burning = False
                if self.fuel_count > 0:
                    self.fuel_count -= 1
                    if self.fuel_count == 0:
                        self.fuel_item = None
                    if self.fuel_item is not None and self.fuel_item in self.fuel_times:
                        self.is_burning = True
                        self.burn_time = self.fuel_times[self.fuel_item]
        
        if self.is_burning and self.input_item is not None and self.input_item in self.recipes and self.input_count > 0:
            self.progress += 0.1
            if self.progress >= self.max_progress:
                self.progress = 0
                
                output_item, output_count = self.recipes[self.input_item]
                
                self.input_count -= 1
                if self.input_count == 0:
                    self.input_item = None
                
                if self.output_item == output_item:
                    if self.output_count + output_count <= 64:
                        self.output_count += output_count
                elif self.output_item is None:
                    self.output_item = output_item
                    self.output_count = output_count
    
    def add_input(self, item_id, count):
        if item_id is not None and item_id in self.recipes and count > 0:
            if self.input_item == item_id:
                if self.input_count + count <= 64:
                    self.input_count += count
                    return True
            elif self.input_item is None:
                self.input_item = item_id
                self.input_count = count
                return True
        return False
    
    def add_fuel(self, item_id, count):
        if item_id is not None and item_id in self.fuel_times and count > 0:
            if self.fuel_item == item_id:
                if self.fuel_count + count <= 64:
                    self.fuel_count += count
                    if not self.is_burning and self.fuel_count > 0:
                        self.is_burning = True
                        self.burn_time = self.fuel_times[item_id]
                    return True
            elif self.fuel_item is None:
                self.fuel_item = item_id
                self.fuel_count = count
                self.is_burning = True
                self.burn_time = self.fuel_times[item_id]
                return True
        return False
    
    def take_output(self):
        if self.output_count > 0:
            item = self.output_item
            count = self.output_count
            self.output_count = 0
            self.output_item = None
            return item, count
        return None, 0

class Game:
    def __init__(self):
        pygame.mixer.init()
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT), pygame.FULLSCREEN)
        pygame.display.set_caption("Teraflat: Mining & Smelting Update")
        self.clock = pygame.time.Clock()
        
        # Новая переменная для F3 режима
        self.show_debug_info = False
        
        try:
            self.font = pygame.font.SysFont("Arial", 24, bold=True)
            self.big_font = pygame.font.SysFont("Arial", 50, bold=True)
            self.small_font = pygame.font.SysFont("Arial", 18, bold=True)
            self.menu_font = pygame.font.SysFont("Arial", 36, bold=True)
            self.debug_font = pygame.font.SysFont("Courier New", 20, bold=True)
        except:
            self.font = pygame.font.Font(None, 24)
            self.big_font = pygame.font.Font(None, 50)
            self.small_font = pygame.font.Font(None, 18)
            self.menu_font = pygame.font.Font(None, 36)
            self.debug_font = pygame.font.Font(None, 20)
        
        self.mod_manager = ModManager(self)
        
        self.state = "MAIN_MENU"
        self.world_type = "LIMITED"
        self.world_h = 600
        
        # Оптимизация:改用 словарь вместо set для быстрого доступа
        self.world = {} 
        self.chunks = {}  # Чанки для оптимизации
        self.generated_terrain = set()
        self.generated_decor = set()
        self.generated_ores = set()
        
        self.seed = random.randint(0, 100000)
        self.biome_offset = random.randint(0, 5000)
        
        self.ash_particles = []
        self.sky_color = [135, 206, 250]
        
        self.game_mode = "SURVIVAL"
        self.creative_flying = False
        self.creative_palette_scroll = 0
        
        # Определение мобильного управления: как только приходит хотя бы
        # одно настоящее touch-событие (FINGERDOWN), считаем что это
        # телефон/планшет и включаем виртуальные джойстик+кнопки; на ПК
        # таких событий не будет вовсе, и это состояние останется False.
        # Определение мобильного управления: проверяем наличие touch-устройств
        # сразу при запуске (pygame.touch), а не только реактивно по первому
        # касанию - иначе на телефоне джойстик не появился бы, пока игрок не
        # догадается тапнуть по экрану вслепую. FINGERDOWN ниже остаётся как
        # резервный путь на случай, если touch-устройство не сообщило о себе
        # заранее (случается на некоторых платформах).
        try:
            self.touch_device_detected = pygame.touch.get_num_devices() > 0
        except Exception:
            self.touch_device_detected = False
        self.joystick_active = False
        self.joystick_origin = (0, 0)
        self.joystick_pos = (0, 0)
        self.joystick_touch_id = None
        self.virtual_move_x = 0.0
        self.virtual_jump_pressed = False   # итог: кнопка прыжка ИЛИ свайп стика вверх
        self.virtual_jump_btn_held = False
        self.virtual_stick_up = False
        self.virtual_touch_ids = {}  # touch_id -> имя кнопки, для мультитач
        self.mobile_action_mode = 'mine'  # 'mine' или 'place' - переключатель для тач-управления
        
        self.health = 20
        self.max_health = 20
        self.timer = 0
        self.death_timer = 0
        self.show_death_screen = False
        
        # Оптимизация физики: вместо полного скана всех 600 блоков высоты
        # мира на каждый x в радиусе игрока (это давало ~14000+ проверок
        # словаря каждые 5 кадров и было главным источником лагов), храним
        # только реально "живые" клетки (песок/пепел/вода/лава), которые
        # нужно проверять. Пересобирается редко (см. update_physics),
        # пополняется на лету по мере распространения жидкости/падения.
        self.active_physics_tiles = set()
        self.last_physics_rescan_x = None
        self.last_physics_rescan_time = 0
        
        self.furnaces = {}
        self.torches = {}
        self.dropped_items = []
        self.door_states = {}
        
        self.darkness_surface = None
        self.light_surface = None
        # Время суток считается в игровых тиках (кадрах), а не в реальном
        # времени (time.time()) - раньше day_time пересчитывался напрямую
        # от time.time() каждый кадр, из-за чего: 1) пауза не действовала
        # на смену дня/ночи (время продолжало идти по системным часам,
        # пока игра была на паузе), 2) сохранённое в файл мира значение
        # тут же перезаписывалось при следующем тике вместо того чтобы
        # реально восстановиться, 3) поведение зависело от того, сколько
        # времени прошло с запуска процесса, а не от игрового прогресса.
        self.day_time_ticks = 120 * FPS
        self.is_night = False
        self.day_night_cycle = True
        self.day_duration = 240  # игровых секунд на полный цикл день+ночь
        self.day_duration_ticks = self.day_duration * FPS
        
        self.hotbar_slots = 9
        self.inventory_slots = 27
        self.selected_slot = 0
        self.inventory_open = False
        self.crafting_table_open = False
        self.furnace_open = None
        self.mods_menu_open = False
        self.mods_select_index = 0
        self.paused = False
        self.settings_open = False
        self.music_volume = 0.4
        self.sound_volume = 0.6
        self.dragging_slider = None
        
        # Графика: пресеты задают режим освещения и дальность прорисовки,
        # дальность по X/Y игрок может потом подкрутить слайдерами.
        # (название, режим света, дальность X, дальность Y) - дальность в тайлах от игрока.
        self.GRAPHICS_PRESETS = [
            ("Супер низкая", "off",    14, 8),
            ("Низкая",       "coarse", 20, 11),
            ("Средняя",      "smooth", 28, 15),
            ("Высокая",      "full",   50, 30),
        ]
        self.VIEW_X_MIN, self.VIEW_X_MAX = 6, 50
        self.VIEW_Y_MIN, self.VIEW_Y_MAX = 4, 30
        # На телефоне по умолчанию "Низкая", на ПК "Высокая"
        self.graphics_quality = 1 if os.environ.get('ANDROID_ARGUMENT') else 3
        self.view_dist_x = self.GRAPHICS_PRESETS[self.graphics_quality][2]
        self.view_dist_y = self.GRAPHICS_PRESETS[self.graphics_quality][3]
        self._light_cache_surf = None
        self._light_cache_key = None
        self._light_cache_tick = 0
        self.settings_sliders = {}
        self.settings_gfx_btns = []
        self.load_settings()
        
        self.inventory_recipes_scroll = 0
        self.crafting_recipes_scroll = 0
        self.max_inventory_recipes_scroll = 0
        self.max_crafting_recipes_scroll = 0
        
        self.dragging_item = None
        self.dragging_count = 0
        self.dragging_from = None
        
        self.hotbar = [None] * self.hotbar_slots
        self.inventory = [None] * self.inventory_slots
        self.hotbar_counts = [0] * self.hotbar_slots
        self.inventory_counts = [0] * self.inventory_slots
        
        self.recipe_hover_info = None
        
        # Кэш для рендеринга
        self.render_cache = {}
        self.last_render_time = 0
        self.render_cache_duration = 0.1  # 100ms кэш
        
        # Добавляем ВСЕ бревна в проходимые блоки
        self.non_solid_blocks = {
            EMPTY, WATER, LAVA, LEAVES, PINE_LEAVES, TORCH, 
            WOOD, PINE_LOG, PINE_WOOD, CACTUS
        }  # GLASS намеренно НЕ здесь: стекло твёрдое, но пропускает свет
        self._lava_light_map = {}
        self._lava_light_key = None
        self._lava_light_tick = 0
        
        self.placeable_blocks = {
            GRASS, DIRT, STONE, SAND, WOOD, PINE_LOG, PLANK, PINE_PLANK,
            LEAVES, PINE_LEAVES, SNOW_GRASS, ASH, CACTUS, 
            CRAFTING_TABLE, GLASS, WOODEN_DOOR, PINE_DOOR,
            FURNACE, STONE_BRICK, IRON_BLOCK, GOLD_BLOCK,
            COAL_ORE, IRON_ORE, GOLD_ORE, TORCH, PINE_WOOD
        }
        
        # Полный список предметов для креативного инвентаря - явно
        # перечислен (не через placeable_blocks), чтобы включить и
        # инструменты/сырьё, и не потащить удалённые из игры ID
        # (железная дверь, алмазы) даже если они где-то ещё числятся.
        self.creative_palette_items = [
            GRASS, DIRT, STONE, SAND, WOOD, PINE_LOG, PLANK, PINE_PLANK,
            LEAVES, PINE_LEAVES, SNOW_GRASS, ASH, CACTUS,
            CRAFTING_TABLE, GLASS, WOODEN_DOOR, PINE_DOOR, FURNACE,
            STONE_BRICK, IRON_BLOCK, GOLD_BLOCK, TORCH,
            COAL_ORE, IRON_ORE, GOLD_ORE,
            STICK, COAL, IRON_INGOT, GOLD_INGOT,
            WOODEN_PICKAXE, WOODEN_AXE, WOODEN_SWORD,
            STONE_PICKAXE, STONE_AXE, STONE_SWORD,
            IRON_PICKAXE, IRON_AXE, IRON_SWORD,
            GOLD_PICKAXE, GOLD_AXE, GOLD_SWORD,
        ]
        
        self.mining_times = {
            GRASS: 0.6, DIRT: 0.6, SAND: 0.6, WOOD: 1.2, PINE_LOG: 1.2,
            LEAVES: 0.3, PINE_LEAVES: 0.3, STONE: 2.2, PLANK: 0.8,
            PINE_PLANK: 0.8, SNOW_GRASS: 0.6, ASH: 0.8, CACTUS: 0.6,
            CRAFTING_TABLE: 0.9, GLASS: 0.5, WOODEN_DOOR: 0.9,
            PINE_DOOR: 0.9, FURNACE: 2.2, COAL_ORE: 2.6, IRON_ORE: 3.2, 
            GOLD_ORE: 4.0, STONE_BRICK: 2.4, IRON_BLOCK: 4.0,
            GOLD_BLOCK: 5.0, TORCH: 0.3, PINE_WOOD: 1.0
        }
        
        self.tool_multipliers = {
            WOODEN_PICKAXE: {"STONE": 2.0, "FURNACE": 2.0, "COAL_ORE": 2.0},
            STONE_PICKAXE: {"STONE": 4.0, "FURNACE": 4.0, "COAL_ORE": 3.0, "IRON_ORE": 3.0},
            IRON_PICKAXE: {"STONE": 6.0, "FURNACE": 6.0, "COAL_ORE": 4.0, "IRON_ORE": 4.0, "GOLD_ORE": 4.0},
            GOLD_PICKAXE: {"STONE": 8.0, "FURNACE": 8.0, "COAL_ORE": 6.0, "IRON_ORE": 6.0, "GOLD_ORE": 6.0},
            WOODEN_AXE: {"WOOD": 2.0, "PINE_LOG": 2.0, "WOODEN_DOOR": 2.0, "PINE_DOOR": 2.0},
            STONE_AXE: {"WOOD": 3.0, "PINE_LOG": 3.0, "WOODEN_DOOR": 3.0, "PINE_DOOR": 3.0},
            IRON_AXE: {"WOOD": 4.0, "PINE_LOG": 4.0, "WOODEN_DOOR": 4.0, "PINE_DOOR": 4.0},
            GOLD_AXE: {"WOOD": 6.0, "PINE_LOG": 6.0, "WOODEN_DOOR": 6.0, "PINE_DOOR": 6.0},
            WOODEN_SWORD: {},
            STONE_SWORD: {},
            IRON_SWORD: {},
            GOLD_SWORD: {},
        }
        
        self.mining_target = None
        self.mining_start_time = 0
        self.mining_progress = 0.0
        self.is_mining = False
        
        self.mining_bar_rect = pygame.Rect(0, 0, 200, 20)
        self.mining_bar_rect.centerx = WIDTH // 2
        self.mining_bar_rect.centery = HEIGHT - 150
        
        self.inventory_recipes = [
            ("plank", "Доски", {WOOD: 1}, PLANK, 4, "Из одного блока дерева получается 4 доски"),
            ("pine_plank", "Еловые доски", {PINE_LOG: 1}, PINE_PLANK, 4, "Из елового бревна получается 4 еловых доски"),
            ("stick", "Палки", {PLANK: 2}, STICK, 4, "2 доски = 4 палки. Основа для инструментов"),
            ("crafting_table", "Верстак", {PLANK: 4}, CRAFTING_TABLE, 1, "4 доски = 1 верстак. Открывает новые рецепты"),
            ("glass", "Стекло", {SAND: 4}, GLASS, 4, "4 песка = 4 стекла. Пропускает свет"),
            ("stone_brick", "Каменный кирпич", {STONE: 4}, STONE_BRICK, 4, "4 камня = 4 каменных кирпича"),
            ("torch", "Факел", {STICK: 1, COAL: 1}, TORCH, 4, "1 палка + 1 уголь = 4 факела. Освещает под землей"),
        ]
        
        self.crafting_table_recipes = [
            ("furnace", "Печка", {STONE: 8}, FURNACE, 1, "8 камня = 1 печка. Для переплавки руд"),
            ("wooden_pickaxe", "Дерев. кирка", {PLANK: 3, STICK: 2}, WOODEN_PICKAXE, 1, "Быстрее добывает камень"),
            ("wooden_axe", "Дерев. топор", {PLANK: 3, STICK: 2}, WOODEN_AXE, 1, "Быстрее рубит дерево"),
            ("wooden_sword", "Дерев. меч", {PLANK: 2, STICK: 1}, WOODEN_SWORD, 1, "Оружие для защиты"),
            ("stone_pickaxe", "Камен. кирка", {STONE: 3, STICK: 2}, STONE_PICKAXE, 1, "В 2 раза быстрее деревянной"),
            ("stone_axe", "Камен. топор", {STONE: 3, STICK: 2}, STONE_AXE, 1, "В 1.5 раза быстрее деревянного"),
            ("stone_sword", "Камен. меч", {STONE: 2, STICK: 1}, STONE_SWORD, 1, "Сильнее деревянного"),
            ("wooden_door", "Дерев. дверь", {PLANK: 6}, WOODEN_DOOR, 3, "6 досок = 3 двери. Открывается ПКМ"),
            ("pine_door", "Еловая дверь", {PINE_PLANK: 6}, PINE_DOOR, 3, "6 еловых досок = 3 еловые двери"),
            ("iron_pickaxe", "Желез. кирка", {IRON_INGOT: 3, STICK: 2}, IRON_PICKAXE, 1, "В 3 раза быстрее каменной"),
            ("iron_axe", "Желез. топор", {IRON_INGOT: 3, STICK: 2}, IRON_AXE, 1, "В 2 раза быстрее каменного"),
            ("iron_sword", "Желез. меч", {IRON_INGOT: 2, STICK: 1}, IRON_SWORD, 1, "Сильнее каменного"),
            ("gold_pickaxe", "Золот. кирка", {GOLD_INGOT: 3, STICK: 2}, GOLD_PICKAXE, 1, "Быстрая, но хрупкая"),
            ("gold_axe", "Золот. топор", {GOLD_INGOT: 3, STICK: 2}, GOLD_AXE, 1, "Быстрый, но хрупкий"),
            ("gold_sword", "Золот. меч", {GOLD_INGOT: 2, STICK: 1}, GOLD_SWORD, 1, "Сильный, но хрупкий"),
            ("iron_block", "Железный блок", {IRON_INGOT: 9}, IRON_BLOCK, 1, "9 слитков = 1 блок железа"),
            ("gold_block", "Золотой блок", {GOLD_INGOT: 9}, GOLD_BLOCK, 1, "9 слитков = 1 блок золота"),
        ]
        
        self.last_click_time = 0
        self.click_cooldown = 0.3
        
        self.save_dir = os.path.join(DATA_DIR, "saves")
        try:
            if not os.path.exists(self.save_dir):
                os.makedirs(self.save_dir)
        except:
            pass
        
        self.worlds_list = []
        self.refresh_worlds_list()
        
        self.current_world_name = ""
        self.world_select_index = 0
        self.world_create_name = ""
        self.world_create_mode = "SURVIVAL"
        self.typing_name = False
        
        self.player_facing = "right"
        self.player_texture_right = None
        self.player_texture_left = None
        self.heart_texture = None
        self.half_heart_texture = None
        self.empty_heart_texture = None
        
        self.textures = {}
        # Кэш масштабированных поверхностей воды/лавы по (block_id, height) -
        # уровень жидкости дискретный (0..MAX_LIQUID_LEVEL), поэтому высот
        # всего 9 вариантов на тип жидкости; без кэша pygame.transform.scale
        # вызывался заново на каждый видимый тайл жидкости каждый кадр.
        self._liquid_surf_cache = {}
        self.door_textures = {
            'wooden_door_closed': None,
            'wooden_door_open': None,
            'iron_door_closed': None,
            'iron_door_open': None,
            'pine_door_closed': None,
            'pine_door_open': None
        }
        self.load_textures()
        self.create_player_textures()
        self.create_heart_textures()
        self.init_lighting()
        
        self.current_music_subfolder = None
        try:
            self.play_random_music("menu")
        except:
            print("Музыка не найдена, продолжаем без музыки")
        
        self.player_rect = pygame.Rect(WIDTH//2, 100, 24, 64)
        self.vel_y = 0
        self.on_ground = False
        self.camera_x = 0
        self.camera_y = 0
        self.is_swimming = False
        self.fall_distance = 0
        self.last_ground_y = self.player_rect.bottom
        
        # Для замера FPS
        self.fps_update_time = time.time()
        self.fps_counter = 0
        self.current_fps = 60

    # Новая функция для отображения debug информации
    def draw_debug_info(self):
        if not self.show_debug_info:
            return
        
        try:
            # Обновляем FPS раз в секунду
            self.fps_counter += 1
            if time.time() - self.fps_update_time >= 1.0:
                self.current_fps = self.fps_counter
                self.fps_counter = 0
                self.fps_update_time = time.time()
            
            # Координаты игрока
            player_x = int(self.player_rect.centerx // TILE_SIZE)
            player_y = int(self.player_rect.centery // TILE_SIZE)
            player_px = int(self.player_rect.x)
            player_py = int(self.player_rect.y)
            
            # Информация о мире
            biome = self.get_biome(player_x)
            chunk_x = player_x // CHUNK_SIZE
            chunk_y = player_y // CHUNK_SIZE
            
            # Создаем полупрозрачный фон - высота с запасом под все строки
            # (раньше surface был 200px при 10 строках по 20px = 200px+,
            # из-за чего последняя строка обрезалась) и ниже HUD-плашки
            # сверху-слева, чтобы не перекрываться с ней.
            debug_surface = pygame.Surface((300, 260), pygame.SRCALPHA)
            debug_surface.fill((0, 0, 0, 180))
            
            # Отображаем информацию
            y_offset = 5
            info_lines = [
                f"FPS: {self.current_fps}",
                f"X: {player_x}  Y: {player_y}",
                f"PX: {player_px}  PY: {player_py}",
                f"Биом: {biome}",
                f"Чанк: ({chunk_x}, {chunk_y})",
                f"Блоков: {len(self.world)}",
                f"Предметов: {len(self.dropped_items)}",
                f"Время: {'День' if not self.is_night else 'Ночь'}",
                f"Режим: {self.game_mode}",
                f"Здоровье: {self.health}/{self.max_health}"
            ]
            
            for line in info_lines:
                text = self.debug_font.render(line, True, (0, 255, 0))
                debug_surface.blit(text, (10, y_offset))
                y_offset += 20
            
            self.screen.blit(debug_surface, (10, 140))
            
        except Exception as e:
            print(f"Ошибка отрисовки debug информации: {e}")

    def create_player_textures(self):
        """Создает текстуры игрока"""
        try:
            # Текстура для правой стороны
            self.player_texture_right = pygame.Surface((24, 64), pygame.SRCALPHA)
            # Голова
            pygame.draw.rect(self.player_texture_right, (224, 172, 105), (4, 0, 16, 16))
            # Глаза
            pygame.draw.rect(self.player_texture_right, (0, 0, 0), (8, 4, 2, 2))
            pygame.draw.rect(self.player_texture_right, (0, 0, 0), (14, 4, 2, 2))
            # Тело
            pygame.draw.rect(self.player_texture_right, (0, 150, 200), (0, 16, 24, 28))
            # Ноги
            pygame.draw.rect(self.player_texture_right, (50, 50, 200), (0, 44, 12, 20))
            pygame.draw.rect(self.player_texture_right, (50, 50, 200), (12, 44, 12, 20))
            # Руки
            pygame.draw.rect(self.player_texture_right, (0, 120, 170), (-4, 20, 4, 20))
            pygame.draw.rect(self.player_texture_right, (0, 120, 170), (24, 20, 4, 20))
            
            # Текстура для левой стороны (отражение)
            self.player_texture_left = pygame.transform.flip(self.player_texture_right, True, False)
            
            # В воде
            self.player_water_texture_right = pygame.Surface((24, 64), pygame.SRCALPHA)
            pygame.draw.rect(self.player_water_texture_right, (224, 172, 105), (4, 0, 16, 16))
            pygame.draw.rect(self.player_water_texture_right, (0, 0, 0), (8, 4, 2, 2))
            pygame.draw.rect(self.player_water_texture_right, (0, 0, 0), (14, 4, 2, 2))
            pygame.draw.rect(self.player_water_texture_right, (50, 100, 255), (0, 16, 24, 28))
            pygame.draw.rect(self.player_water_texture_right, (30, 70, 255), (0, 44, 12, 20))
            pygame.draw.rect(self.player_water_texture_right, (30, 70, 255), (12, 44, 12, 20))
            pygame.draw.rect(self.player_water_texture_right, (40, 80, 220), (-4, 20, 4, 20))
            pygame.draw.rect(self.player_water_texture_right, (40, 80, 220), (24, 20, 4, 20))
            
            self.player_water_texture_left = pygame.transform.flip(self.player_water_texture_right, True, False)
        except:
            # Запасной вариант если не удалось создать текстуры
            self.player_texture_right = pygame.Surface((24, 64))
            self.player_texture_right.fill((0, 150, 200))
            self.player_texture_left = self.player_texture_right.copy()
            self.player_water_texture_right = pygame.Surface((24, 64))
            self.player_water_texture_right.fill((50, 100, 255))
            self.player_water_texture_left = self.player_water_texture_right.copy()

    def create_heart_textures(self):
        """Создает текстуры сердец"""
        try:
            self.heart_texture = pygame.Surface((20, 20), pygame.SRCALPHA)
            # Полное сердце
            pygame.draw.polygon(self.heart_texture, (255, 0, 0), [
                (10, 4), (6, 0), (2, 4), (0, 8), (10, 18), (20, 8), (18, 4), (14, 0)
            ])
            pygame.draw.polygon(self.heart_texture, (255, 100, 100), [
                (10, 6), (7, 3), (4, 6), (3, 9), (10, 16), (17, 9), (16, 6), (13, 3)
            ], 1)
            
            self.half_heart_texture = pygame.Surface((20, 20), pygame.SRCALPHA)
            # Половина сердца
            pygame.draw.polygon(self.half_heart_texture, (255, 0, 0), [
                (10, 4), (6, 0), (2, 4), (0, 8), (10, 18), (20, 8), (18, 4), (14, 0)
            ])
            # Левая половина закрашена, правая пустая
            mask = pygame.Surface((20, 20), pygame.SRCALPHA)
            mask.fill((0, 0, 0))
            pygame.draw.polygon(mask, (255, 255, 255), [
                (10, 4), (6, 0), (2, 4), (0, 8), (10, 18)
            ])
            self.half_heart_texture.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
            
            self.empty_heart_texture = pygame.Surface((20, 20), pygame.SRCALPHA)
            # Пустое сердце (контур)
            pygame.draw.polygon(self.empty_heart_texture, (50, 0, 0), [
                (10, 4), (6, 0), (2, 4), (0, 8), (10, 18), (20, 8), (18, 4), (14, 0)
            ], 2)
        except:
            # Запасной вариант
            self.heart_texture = pygame.Surface((20, 20))
            self.heart_texture.fill((255, 0, 0))
            self.half_heart_texture = pygame.Surface((20, 20))
            self.half_heart_texture.fill((255, 100, 100))
            self.empty_heart_texture = pygame.Surface((20, 20))
            self.empty_heart_texture.fill((100, 0, 0))

    def settings_path(self):
        return os.path.join(DATA_DIR, "settings.json")

    def load_settings(self):
        """Читает сохранённые настройки (громкость, графика, дальность)."""
        try:
            path = self.settings_path()
            if not os.path.exists(path):
                return
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            self.music_volume = max(0.0, min(1.0, float(data.get('music_volume', self.music_volume))))
            self.sound_volume = max(0.0, min(1.0, float(data.get('sound_volume', self.sound_volume))))
            q = int(data.get('graphics_quality', self.graphics_quality))
            self.graphics_quality = max(0, min(len(self.GRAPHICS_PRESETS) - 1, q))
            self.view_dist_x = max(self.VIEW_X_MIN, min(self.VIEW_X_MAX, int(data.get('view_dist_x', self.view_dist_x))))
            self.view_dist_y = max(self.VIEW_Y_MIN, min(self.VIEW_Y_MAX, int(data.get('view_dist_y', self.view_dist_y))))
        except Exception as e:
            print(f"Не удалось прочитать настройки: {e}")

    def save_settings(self):
        try:
            with open(self.settings_path(), 'w', encoding='utf-8') as f:
                json.dump({
                    'music_volume': self.music_volume,
                    'sound_volume': self.sound_volume,
                    'graphics_quality': self.graphics_quality,
                    'view_dist_x': self.view_dist_x,
                    'view_dist_y': self.view_dist_y,
                }, f)
        except Exception as e:
            print(f"Не удалось сохранить настройки: {e}")

    def set_graphics_quality(self, q):
        q = max(0, min(len(self.GRAPHICS_PRESETS) - 1, q))
        self.graphics_quality = q
        self.view_dist_x = self.GRAPHICS_PRESETS[q][2]
        self.view_dist_y = self.GRAPHICS_PRESETS[q][3]
        self._light_cache_key = None  # сбросить кэш освещения

    def get_view_tile_box(self):
        """Окно дальности прорисовки в тайлах: пересечение экрана и области
        +-view_dist вокруг игрока. Возвращает (x0, y0, x1, y1), x1/y1 не включены."""
        T = TILE_SIZE
        sx = int(self.camera_x // T) - 1
        sy = int(self.camera_y // T) - 1
        ex = sx + WIDTH // T + 3
        ey = sy + HEIGHT // T + 3
        px = int(self.player_rect.centerx // T)
        py = int(self.player_rect.centery // T)
        x0 = max(sx, px - self.view_dist_x)
        x1 = min(ex, px + self.view_dist_x + 1)
        y0 = max(sy, py - self.view_dist_y)
        y1 = min(ey, py + self.view_dist_y + 1)
        if x1 <= x0:
            x1 = x0 + 1
        if y1 <= y0:
            y1 = y0 + 1
        return x0, y0, x1, y1

    def draw_view_frame(self, box):
        """Закрашивает чёрным всё за пределами дальности прорисовки."""
        T = TILE_SIZE
        bx0, by0, bx1, by1 = box
        l = int(bx0 * T - self.camera_x)
        t = int(by0 * T - self.camera_y)
        r = int(bx1 * T - self.camera_x)
        b = int(by1 * T - self.camera_y)
        if l <= 0 and t <= 0 and r >= WIDTH and b >= HEIGHT:
            return
        black = (0, 0, 0)
        scr = self.screen
        if t > 0:
            scr.fill(black, (0, 0, WIDTH, min(t, HEIGHT)))
        if b < HEIGHT:
            b0 = max(b, 0)
            scr.fill(black, (0, b0, WIDTH, HEIGHT - b0))
        ymin, ymax = max(t, 0), min(b, HEIGHT)
        if ymax > ymin:
            if l > 0:
                scr.fill(black, (0, ymin, min(l, WIDTH), ymax - ymin))
            if r < WIDTH:
                r0 = max(r, 0)
                scr.fill(black, (r0, ymin, WIDTH - r0, ymax - ymin))

    def init_lighting(self):
        self.darkness_surface = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        self.light_surface = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        
    def _is_column_underground(self, x, y, ceiling_cache):
        """Возвращает True, если над (x, y) есть хотя бы один сплошной блок
        (не считая факелов/стекла) где-то выше по этой колонке - то есть
        сюда не проникает открытое небо. Результат кэшируется по колонке
        на время одного вызова apply_lighting, чтобы не пересканировать
        всю колонку заново для каждого y (что было O(height^2))."""
        col = ceiling_cache.get(x)
        if col is None:
            col = {}
            solid_found_at = None
            for check_y in range(0, y + 60):
                if (x, check_y) in self.world:
                    block_id = self.world[(x, check_y)][0]
                    if block_id not in self.non_solid_blocks and block_id != TORCH and block_id != GLASS:
                        solid_found_at = check_y
                        break
            col['ceiling_y'] = solid_found_at
            ceiling_cache[x] = col
        ceiling_y = col.get('ceiling_y')
        return ceiling_y is not None and ceiling_y < y

    def get_light_level_at(self, x, y, ceiling_cache=None):
        if ceiling_cache is None:
            ceiling_cache = {}
        light_level = 0
        
        is_underground = self._is_column_underground(x, y, ceiling_cache)
        
        if is_underground:
            light_level = 1
        else:
            if not self.is_night:
                light_level = 15
            else:
                light_level = 4
        
        # Свет проникает и по бокам, если там нет сплошной стены - проверяем
        # соседние колонки слева/справа: если хотя бы одна не "подземная"
        # (открыта небу) и текущая клетка сама не закрыта твёрдым блоком,
        # то немного света просачивается сюда сбоку.
        if is_underground:
            here_block = self.world.get((x, y))
            here_solid = here_block is not None and here_block[0] not in self.non_solid_blocks and here_block[0] != TORCH and here_block[0] != GLASS
            if not here_solid:
                for side_dx in (-1, 1):
                    side_x = x + side_dx
                    side_underground = self._is_column_underground(side_x, y, ceiling_cache)
                    if not side_underground:
                        side_light = 15 if not self.is_night else 4
                        light_level = max(light_level, side_light * 0.5)
        
        lava_light = self._lava_light_map.get((x, y), 0)
        if lava_light > light_level:
            light_level = lava_light
        
        for torch_pos, torch in self.torches.items():
            torch_x, torch_y = torch_pos
            # Быстрый отсев по bounding box перед дорогим sqrt
            if abs(x - torch_x) > torch.light_level or abs(y - torch_y) > torch.light_level:
                continue
            distance = math.sqrt((x - torch_x) ** 2 + (y - torch_y) ** 2)
            if distance <= torch.light_level:
                torch_light = torch.current_light * (1 - distance / torch.light_level)
                light_level = max(light_level, torch_light)
        
        return min(15, max(0, light_level))

    def _rebuild_lava_light(self, sx, sy, ex, ey):
        """Лава светится: карта освещения от открытых клеток лавы (радиус 5).
        Пересчитывается при смещении камеры на тайл или раз в ~10 кадров."""
        self._lava_light_tick += 1
        key = (sx, sy)
        if key == self._lava_light_key and self._lava_light_tick % 10:
            return
        self._lava_light_key = key
        R = 5
        light_map = {}
        world = self.world
        for lx in range(sx - R, ex + R):
            for ly in range(sy - R, ey + R):
                b = world.get((lx, ly))
                if b is None or b[0] != LAVA:
                    continue
                # только открытая лава (есть не-лавовый сосед) - внутренняя не нужна
                exposed = False
                for nx, ny in ((lx + 1, ly), (lx - 1, ly), (lx, ly + 1), (lx, ly - 1)):
                    nb = world.get((nx, ny))
                    if nb is None or nb[0] != LAVA:
                        exposed = True
                        break
                if not exposed:
                    continue
                for dx in range(-R, R + 1):
                    for dy in range(-R, R + 1):
                        d = math.sqrt(dx * dx + dy * dy)
                        if d > R:
                            continue
                        v = 13 * (1 - d / (R + 1))
                        pos = (lx + dx, ly + dy)
                        if v > light_map.get(pos, 0):
                            light_map[pos] = v
        self._lava_light_map = light_map

    def apply_lighting(self, box=None):
        """Освещение. Режим зависит от графики:
        off    - один общий тёмный слой ночью/под землёй (без поблочного света);
        coarse - свет считается на блок 2x2 тайла, сглаживается, обновляется редко;
        smooth - свет на каждый тайл, сглаживается, обновляется раз в пару кадров;
        full   - свет на каждый тайл каждый кадр (как раньше)."""
        try:
            mode = self.GRAPHICS_PRESETS[self.graphics_quality][1]
            max_darkness_alpha = 220  # максимальная темнота там, где света совсем нет
            T = TILE_SIZE
            if box is None:
                box = self.get_view_tile_box()
            bx0, by0, bx1, by1 = box
            
            if mode == "off":
                # Одна проверка вместо тысяч: темно ли вокруг игрока
                px = int(self.player_rect.centerx // T)
                py = int(self.player_rect.centery // T)
                light = self.get_light_level_at(px, py, {})
                alpha = int(max_darkness_alpha * 0.65 * (1 - light / 15))
                if alpha > 0:
                    if self.darkness_surface is None or self.darkness_surface.get_size() != (WIDTH, HEIGHT):
                        self.init_lighting()
                    self.darkness_surface.fill((0, 0, 0, alpha))
                    self.screen.blit(self.darkness_surface, (0, 0))
                return
            
            self._rebuild_lava_light(bx0, by0, bx1, by1)
            
            if mode == "full":
                self.darkness_surface.fill((0, 0, 0, 0))
                ceiling_cache = {}
                for tx in range(bx0, bx1):
                    for ty in range(by0, by1):
                        light = self.get_light_level_at(tx, ty, ceiling_cache)
                        alpha = int(max_darkness_alpha * (1 - light / 15))
                        if alpha > 0:
                            rx = tx * T - self.camera_x
                            ry = ty * T - self.camera_y
                            pygame.draw.rect(self.darkness_surface, (0, 0, 0, alpha),
                                            (rx, ry, T, T))
                self.screen.blit(self.darkness_surface, (0, 0))
                return
            
            # coarse / smooth: считаем свет в маленькую поверхность (1 пиксель
            # = 1 клетка света), растягиваем с интерполяцией и кэшируем.
            step = 2 if mode == "coarse" else 1
            interval = 6 if mode == "coarse" else 3
            x0 = bx0 - (bx0 % step)
            y0 = by0 - (by0 % step)
            key = (x0, y0, bx1, by1, step)
            self._light_cache_tick += 1
            if key != self._light_cache_key or self._light_cache_tick >= interval or self._light_cache_surf is None:
                self._light_cache_tick = 0
                self._light_cache_key = key
                cols = (bx1 - x0 + step - 1) // step
                rows = (by1 - y0 + step - 1) // step
                small = pygame.Surface((cols, rows), pygame.SRCALPHA)
                ceiling_cache = {}
                for cx in range(cols):
                    tx = x0 + cx * step
                    for cy in range(rows):
                        ty = y0 + cy * step
                        light = self.get_light_level_at(tx, ty, ceiling_cache)
                        alpha = int(max_darkness_alpha * (1 - light / 15))
                        small.set_at((cx, cy), (0, 0, 0, alpha))
                size = (cols * step * T, rows * step * T)
                if cols * rows > 1:
                    self._light_cache_surf = pygame.transform.smoothscale(small, size)
                else:
                    self._light_cache_surf = pygame.transform.scale(small, size)
            self.screen.blit(self._light_cache_surf, (x0 * T - self.camera_x, y0 * T - self.camera_y))
        except Exception:
            pass

    def update_lighting(self):
        try:
            if self.day_night_cycle and not self.paused:
                self.day_time_ticks = (self.day_time_ticks + 1) % self.day_duration_ticks
                day_time_seconds = self.day_time_ticks / FPS
                self.is_night = not (60 < day_time_seconds < 180)
            
            for torch in list(self.torches.values()):
                torch.update()
        except:
            pass

    def refresh_worlds_list(self):
        self.worlds_list = []
        if os.path.exists(self.save_dir):
            try:
                for folder in os.listdir(self.save_dir):
                    folder_path = os.path.join(self.save_dir, folder)
                    if os.path.isdir(folder_path):
                        info_file = os.path.join(folder_path, "world.info")
                        if os.path.exists(info_file):
                            try:
                                with open(info_file, 'r') as f:
                                    info = json.load(f)
                                    self.worlds_list.append({
                                        'name': folder,
                                        'last_played': info.get('last_played', 'Неизвестно'),
                                        'world_type': info.get('world_type', 'LIMITED')
                                    })
                            except:
                                self.worlds_list.append({
                                    'name': folder,
                                    'last_played': 'Ошибка загрузки',
                                    'world_type': 'LIMITED'
                                })
            except Exception as e:
                print(f"Ошибка при обновлении списка миров: {e}")
        
        self.worlds_list.sort(key=lambda x: x.get('last_played', ''), reverse=True)

    def save_world(self):
        if not self.current_world_name:
            return False
        
        world_path = os.path.join(self.save_dir, self.current_world_name)
        try:
            if not os.path.exists(world_path):
                os.makedirs(world_path)
        except:
            return False
        
        try:
            info = {
                'seed': self.seed,
                'world_type': self.world_type,
                'game_mode': self.game_mode,
                'biome_offset': self.biome_offset,
                'last_played': time.strftime("%Y-%m-%d %H:%M:%S"),
                'health': self.health,
                'max_health': self.max_health,
                'day_time_ticks': self.day_time_ticks,
                'is_night': self.is_night,
                'day_night_cycle': self.day_night_cycle
            }
            
            with open(os.path.join(world_path, "world.info"), 'w') as f:
                json.dump(info, f)
            
            player_data = {
                'pos': (self.player_rect.x, self.player_rect.y),
                'vel_y': self.vel_y,
                'camera': (self.camera_x, self.camera_y),
                'health': self.health,
                'selected_slot': self.selected_slot,
                'player_facing': self.player_facing
            }
            
            with open(os.path.join(world_path, "player.dat"), 'wb') as f:
                pickle.dump(player_data, f)
            
            inv_data = {
                'hotbar': self.hotbar,
                'inventory': self.inventory,
                'hotbar_counts': self.hotbar_counts,
                'inventory_counts': self.inventory_counts
            }
            
            with open(os.path.join(world_path, "inventory.dat"), 'wb') as f:
                pickle.dump(inv_data, f)
            
            # Преобразуем множества в списки для сериализации
            world_data = {
                'world': self.world,
                'generated_terrain': list(self.generated_terrain),
                'generated_decor': list(self.generated_decor),
                'generated_ores': list(self.generated_ores)
            }
            
            with open(os.path.join(world_path, "world.dat"), 'wb') as f:
                pickle.dump(world_data, f)
            
            furnace_data = {}
            for pos, furnace in self.furnaces.items():
                furnace_data[str(pos)] = {
                    'input_item': furnace.input_item,
                    'input_count': furnace.input_count,
                    'fuel_item': furnace.fuel_item,
                    'fuel_count': furnace.fuel_count,
                    'output_item': furnace.output_item,
                    'output_count': furnace.output_count,
                    'is_burning': furnace.is_burning,
                    'burn_time': furnace.burn_time,
                    'progress': furnace.progress
                }
            
            with open(os.path.join(world_path, "furnaces.dat"), 'wb') as f:
                pickle.dump(furnace_data, f)
            
            torch_data = {}
            for pos in self.torches:
                torch_data[str(pos)] = True
            
            with open(os.path.join(world_path, "torches.dat"), 'wb') as f:
                pickle.dump(torch_data, f)
            
            with open(os.path.join(world_path, "doors.dat"), 'wb') as f:
                pickle.dump(self.door_states, f)
            
            print(f"Мир '{self.current_world_name}' сохранен!")
            return True
            
        except Exception as e:
            print(f"Ошибка сохранения мира: {e}")
            return False

    def load_world(self, world_name):
        self.paused = False
        self.settings_open = False
        world_path = os.path.join(self.save_dir, world_name)
        
        if not os.path.exists(world_path):
            print(f"Мир '{world_name}' не найден!")
            return False
        
        try:
            with open(os.path.join(world_path, "world.info"), 'r') as f:
                info = json.load(f)
                self.seed = info['seed']
                self.world_type = info['world_type']
                self.game_mode = info.get('game_mode', 'SURVIVAL')
                self.creative_flying = False
                self.biome_offset = info['biome_offset']
                self.health = info.get('health', 20)
                self.max_health = info.get('max_health', 20)
                if 'day_time_ticks' in info:
                    self.day_time_ticks = info['day_time_ticks']
                else:
                    # Старое сохранение (до перехода на тиковую систему) -
                    # конвертируем секунды в тики, чтобы не терять прогресс.
                    self.day_time_ticks = int(info.get('day_time', 120) * FPS)
                self.is_night = info.get('is_night', False)
                self.day_night_cycle = info.get('day_night_cycle', True)
            
            with open(os.path.join(world_path, "player.dat"), 'rb') as f:
                player_data = pickle.load(f)
                self.player_rect.x, self.player_rect.y = player_data['pos']
                self.vel_y = player_data['vel_y']
                self.camera_x, self.camera_y = player_data['camera']
                self.health = player_data.get('health', 20)
                self.selected_slot = player_data.get('selected_slot', 0)
                self.player_facing = player_data.get('player_facing', 'right')
            
            with open(os.path.join(world_path, "inventory.dat"), 'rb') as f:
                inv_data = pickle.load(f)
                self.hotbar = inv_data['hotbar']
                self.inventory = inv_data['inventory']
                self.hotbar_counts = inv_data['hotbar_counts']
                self.inventory_counts = inv_data['inventory_counts']
            
            with open(os.path.join(world_path, "world.dat"), 'rb') as f:
                world_data = pickle.load(f)
                self.world = world_data['world']
                self.generated_terrain = set(world_data['generated_terrain'])
                self.generated_decor = set(world_data['generated_decor'])
                self.generated_ores = set(world_data['generated_ores'])
            
            self.furnaces = {}
            furnace_path = os.path.join(world_path, "furnaces.dat")
            if os.path.exists(furnace_path):
                with open(furnace_path, 'rb') as f:
                    furnace_data = pickle.load(f)
                    for pos_str, data in furnace_data.items():
                        # Преобразуем строку обратно в кортеж
                        pos = eval(pos_str)
                        furnace = Furnace(pos[0], pos[1])
                        furnace.input_item = data['input_item']
                        furnace.input_count = data['input_count']
                        furnace.fuel_item = data['fuel_item']
                        furnace.fuel_count = data['fuel_count']
                        furnace.output_item = data['output_item']
                        furnace.output_count = data['output_count']
                        furnace.is_burning = data['is_burning']
                        furnace.burn_time = data['burn_time']
                        furnace.progress = data['progress']
                        self.furnaces[pos] = furnace
            
            self.torches = {}
            torch_path = os.path.join(world_path, "torches.dat")
            if os.path.exists(torch_path):
                with open(torch_path, 'rb') as f:
                    torch_data = pickle.load(f)
                    for pos_str in torch_data:
                        pos = eval(pos_str)
                        self.torches[pos] = Torch(pos[0], pos[1])
            
            self.door_states = {}
            door_path = os.path.join(world_path, "doors.dat")
            if os.path.exists(door_path):
                with open(door_path, 'rb') as f:
                    self.door_states = pickle.load(f)
            
            px = int(self.player_rect.centerx // TILE_SIZE)
            for x in range(px - UPDATE_DISTANCE, px + UPDATE_DISTANCE):
                if x not in self.generated_terrain:
                    self.generate_chunk(x)
            for x in range(px - RENDER_DISTANCE, px + RENDER_DISTANCE):
                if x not in self.generated_decor:
                    self.plant_decor(x)
            
            self.current_world_name = world_name
            self.show_death_screen = False
            print(f"Мир '{world_name}' загружен!")
            return True
            
        except Exception as e:
            print(f"Ошибка загрузки мира: {e}")
            return False

    def delete_world(self, world_name):
        world_path = os.path.join(self.save_dir, world_name)
        
        if os.path.exists(world_path):
            try:
                shutil.rmtree(world_path)
            except:
                pass
            self.refresh_worlds_list()
            return True
        return False

    def play_music(self, filename):
        try:
            music_path = os.path.join("Music", filename)
            if os.path.exists(music_path):
                pygame.mixer.music.stop()
                pygame.mixer.music.load(music_path)
                pygame.mixer.music.set_volume(self.music_volume)
                pygame.mixer.music.play(-1)
        except Exception as e:
            print(f"Ошибка загрузки музыки: {e}")

    def play_random_music(self, subfolder):
        """Играет случайный трек из Music/<subfolder> (например 'menu' или 'game')"""
        try:
            folder_path = os.path.join("Music", subfolder)
            if not os.path.exists(folder_path):
                print(f"Музыка: папка '{folder_path}' не найдена - положите туда .mp3/.ogg/.wav файлы")
                return
            tracks = [f for f in os.listdir(folder_path)
                      if f.lower().endswith(('.mp3', '.ogg', '.wav'))]
            if not tracks:
                print(f"Музыка: папка '{folder_path}' пуста - нет .mp3/.ogg/.wav файлов")
                return
            chosen = random.choice(tracks)
            track_path = os.path.join(folder_path, chosen)
            
            # Отвязываем end-event ПЕРЕД остановкой: иначе stop() на текущем
            # треке иногда сам вызывает событие конца (в зависимости от
            # платформы/бэкенда SDL_mixer), и MUSIC_END_EVENT прилетает уже
            # после того как мы поставили новый трек - обработчик события
            # запускает play_random_music(current_music_subfolder) заново и
            # либо обрывает только что стартовавший трек, либо просто не
            # даёт звуку начаться на некоторых платформах. Это и объясняло
            # "музыка молчит, пока не нажмёшь М" - к моменту открытия меню
            # модов проблемная гонка уже была вызвана чем-то другим (сменой
            # состояния) и трек наконец заводился.
            pygame.mixer.music.set_endevent()
            pygame.mixer.music.stop()
            try:
                pygame.mixer.music.unload()
            except Exception:
                pass  # unload доступен не во всех версиях pygame - не критично
            pygame.mixer.music.load(track_path)
            pygame.mixer.music.set_volume(self.music_volume)
            pygame.mixer.music.play(0)
            pygame.mixer.music.set_endevent(MUSIC_END_EVENT)
            self.current_music_subfolder = subfolder
        except Exception as e:
            print(f"Ошибка загрузки случайной музыки: {e}")

    def play_damage_sound(self):
        try:
            sound_path = os.path.join("Music", "damage.mp3")
            if os.path.exists(sound_path):
                dmg_sound = pygame.mixer.Sound(sound_path)
                dmg_sound.set_volume(0.6 * self.sound_volume)
                dmg_sound.play()
        except:
            pass

    def play_collect_sound(self):
        try:
            sound_path = os.path.join("Music", "collect.mp3")
            if os.path.exists(sound_path):
                collect_sound = pygame.mixer.Sound(sound_path)
                collect_sound.set_volume(0.3 * self.sound_volume)
                collect_sound.play()
        except:
            pass

    def play_death_sound(self):
        try:
            sound_path = os.path.join("Music", "death.mp3")
            if os.path.exists(sound_path):
                death_sound = pygame.mixer.Sound(sound_path)
                death_sound.set_volume(0.7 * self.sound_volume)
                death_sound.play()
        except:
            pass

    def load_textures(self):
        texture_files = {
            GRASS: "grass.png", DIRT: "dirt.png", STONE: "stone.png",
            WATER: "water.png", LAVA: "lava.png", WOOD: "wood.png",
            LEAVES: "leaves.png", SAND: "sand.png", PLANK: "plank.png",
            PINE_PLANK: "pine_plank.png",
            SNOW_GRASS: "snow.png", ASH: "ash.png", CACTUS: "cactus.png",
            PINE_LEAVES: "pine_leaves.png", PINE_LOG: "pine_log.png",
            STICK: "stick.png", CRAFTING_TABLE: "crafting_table.png",
            WOODEN_PICKAXE: "wooden_pickaxe.png", WOODEN_AXE: "wooden_axe.png", 
            WOODEN_SWORD: "wooden_sword.png",
            STONE_PICKAXE: "stone_pickaxe.png", STONE_AXE: "stone_axe.png", 
            STONE_SWORD: "stone_sword.png",
            GLASS: "glass.png", 
            FURNACE: "furnace.png", COAL_ORE: "coal_ore.png",
            IRON_ORE: "iron_ore.png", GOLD_ORE: "gold_ore.png",
            COAL: "coal.png", IRON_INGOT: "iron_ingot.png",
            GOLD_INGOT: "gold_ingot.png",
            IRON_PICKAXE: "iron_pickaxe.png", IRON_AXE: "iron_axe.png",
            IRON_SWORD: "iron_sword.png",
            GOLD_PICKAXE: "gold_pickaxe.png", GOLD_AXE: "gold_axe.png",
            GOLD_SWORD: "gold_sword.png",
            STONE_BRICK: "stone_brick.png", IRON_BLOCK: "iron_block.png",
            GOLD_BLOCK: "gold_block.png",
            TORCH: "torch.png",
            PINE_WOOD: "pine_wood.png",
        }
        
        # Словари для текстур дверей
        closed_door_files = {
            "wooden_door_closed": "wooden_door_closed.png",
            "iron_door_closed": "iron_door_closed.png",
            "pine_door_closed": "pine_door_closed.png"
        }
        
        open_door_files = {
            "wooden_door_open": "wooden_door_open.png",
            "iron_door_open": "iron_door_open.png",
            "pine_door_open": "pine_door_open.png"
        }
        
        fallback_colors = {
            GRASS: (34, 177, 76), DIRT: (139, 69, 19), STONE: (120, 120, 120),
            WATER: (0, 100, 255, 180), LAVA: (255, 69, 0), WOOD: (101, 67, 33),
            LEAVES: (40, 120, 40), SAND: (240, 230, 140), PLANK: (180, 150, 100),
            PINE_PLANK: (80, 60, 40),
            SNOW_GRASS: (240, 240, 255), ASH: (40, 40, 40), CACTUS: (0, 150, 0),
            PINE_LEAVES: (15, 45, 15), PINE_LOG: (45, 30, 15),
            STICK: (160, 120, 60), CRAFTING_TABLE: (150, 100, 50),
            WOODEN_PICKAXE: (139, 90, 43), WOODEN_AXE: (139, 90, 43), 
            WOODEN_SWORD: (139, 90, 43),
            STONE_PICKAXE: (150, 150, 150), STONE_AXE: (150, 150, 150), 
            STONE_SWORD: (150, 150, 150),
            GLASS: (200, 220, 255, 128),
            FURNACE: (100, 100, 100), COAL_ORE: (50, 50, 50),
            IRON_ORE: (180, 120, 80), GOLD_ORE: (255, 215, 0),
            COAL: (30, 30, 30), IRON_INGOT: (180, 180, 180),
            GOLD_INGOT: (255, 215, 0),
            IRON_PICKAXE: (180, 180, 180), IRON_AXE: (180, 180, 180),
            IRON_SWORD: (180, 180, 180),
            GOLD_PICKAXE: (255, 215, 0), GOLD_AXE: (255, 215, 0),
            GOLD_SWORD: (255, 215, 0),
            STONE_BRICK: (140, 140, 140), IRON_BLOCK: (200, 200, 200),
            GOLD_BLOCK: (255, 225, 50),
            TORCH: (255, 200, 0),
            PINE_WOOD: (80, 60, 40),
        }
        
        # Загружаем обычные текстуры
        for b_id, filename in texture_files.items():
            path = os.path.join("Textures", filename)
            
            try:
                if os.path.exists(path):
                    try:
                        img = pygame.image.load(path).convert_alpha()
                    except:
                        img = pygame.image.load(path).convert()
                    
                    if b_id == TORCH:
                        self.textures[b_id] = pygame.transform.scale(img, (TILE_SIZE // 2, TILE_SIZE))
                    elif b_id == GLASS:
                        img = img.copy()
                        img.set_alpha(180)
                        self.textures[b_id] = pygame.transform.scale(img, (TILE_SIZE, TILE_SIZE))
                    elif b_id == CRAFTING_TABLE:
                        # Верстак шире клетки: 2 тайла в ширину, 1 в высоту -
                        # рисуется как дверь: физически одна клетка в мире,
                        # но текстура растянута и смещена при отрисовке.
                        self.textures[b_id] = pygame.transform.scale(img, (TILE_SIZE * 2, TILE_SIZE))
                    elif b_id == FURNACE:
                        # Печка выше клетки: 1 тайл в ширину, 2 в высоту.
                        self.textures[b_id] = pygame.transform.scale(img, (TILE_SIZE, TILE_SIZE * 2))
                    else:
                        self.textures[b_id] = pygame.transform.scale(img, (TILE_SIZE, TILE_SIZE))
                else:
                    self.create_fallback_texture(b_id, fallback_colors.get(b_id, (255, 255, 255)))
            except Exception as e:
                print(f"Ошибка загрузки текстуры {filename}: {e}")
                self.create_fallback_texture(b_id, fallback_colors.get(b_id, (255, 255, 255)))
        
        # Загружаем текстуры закрытых дверей
        for door_key, filename in closed_door_files.items():
            path = os.path.join("Textures", filename)
            try:
                if os.path.exists(path):
                    img = pygame.image.load(path).convert_alpha()
                    self.door_textures[door_key] = pygame.transform.scale(img, (TILE_SIZE, TILE_SIZE * 2))
                else:
                    # Если файла нет, создаем текстуру программно
                    if door_key == "wooden_door_closed":
                        self.door_textures[door_key] = self.create_door_texture(WOODEN_DOOR, False)
                    elif door_key == "iron_door_closed":
                        self.door_textures[door_key] = self.create_door_texture(IRON_DOOR, False)
                    elif door_key == "pine_door_closed":
                        self.door_textures[door_key] = self.create_door_texture(PINE_DOOR, False)
            except Exception as e:
                print(f"Ошибка загрузки текстуры двери {filename}: {e}")
                if door_key == "wooden_door_closed":
                    self.door_textures[door_key] = self.create_door_texture(WOODEN_DOOR, False)
                elif door_key == "iron_door_closed":
                    self.door_textures[door_key] = self.create_door_texture(IRON_DOOR, False)
                elif door_key == "pine_door_closed":
                    self.door_textures[door_key] = self.create_door_texture(PINE_DOOR, False)
        
        # Загружаем текстуры открытых дверей
        for door_key, filename in open_door_files.items():
            path = os.path.join("Textures", filename)
            try:
                if os.path.exists(path):
                    img = pygame.image.load(path).convert_alpha()
                    self.door_textures[door_key] = pygame.transform.scale(img, (TILE_SIZE, TILE_SIZE * 2))
                else:
                    # Если файла нет, создаем текстуру программно
                    if door_key == "wooden_door_open":
                        self.door_textures[door_key] = self.create_door_texture(WOODEN_DOOR, True)
                    elif door_key == "iron_door_open":
                        self.door_textures[door_key] = self.create_door_texture(IRON_DOOR, True)
                    elif door_key == "pine_door_open":
                        self.door_textures[door_key] = self.create_door_texture(PINE_DOOR, True)
            except Exception as e:
                print(f"Ошибка загрузки текстуры двери {filename}: {e}")
                if door_key == "wooden_door_open":
                    self.door_textures[door_key] = self.create_door_texture(WOODEN_DOOR, True)
                elif door_key == "iron_door_open":
                    self.door_textures[door_key] = self.create_door_texture(IRON_DOOR, True)
                elif door_key == "pine_door_open":
                    self.door_textures[door_key] = self.create_door_texture(PINE_DOOR, True)
        
        # Устанавливаем текстуры для ID дверей по умолчанию (закрытые)
        self.textures[WOODEN_DOOR] = self.door_textures["wooden_door_closed"]
        self.textures[IRON_DOOR] = self.door_textures["iron_door_closed"]
        self.textures[PINE_DOOR] = self.door_textures["pine_door_closed"]
        
        try:
            self.textures = self.mod_manager.apply_mod_textures(self.textures)
        except Exception as e:
            print(f"Ошибка при применении текстур модов: {e}")

    def create_door_texture(self, door_type, is_open):
        """Создает текстуру двери программно"""
        try:
            surf = pygame.Surface((TILE_SIZE, TILE_SIZE * 2), pygame.SRCALPHA)
            
            if door_type == WOODEN_DOOR:
                if is_open:
                    base_color = (139, 90, 43, 200)  # Полупрозрачный
                    detail_color = (120, 80, 40, 200)
                else:
                    base_color = (139, 90, 43)
                    detail_color = (120, 80, 40)
            elif door_type == PINE_DOOR:
                if is_open:
                    base_color = (80, 60, 40, 200)  # Полупрозрачный
                    detail_color = (60, 45, 30, 200)
                else:
                    base_color = (80, 60, 40)
                    detail_color = (60, 45, 30)
            else:  # IRON_DOOR
                if is_open:
                    base_color = (150, 150, 150, 200)  # Полупрозрачный
                    detail_color = (120, 120, 120, 200)
                else:
                    base_color = (150, 150, 150)
                    detail_color = (120, 120, 120)
            
            surf.fill(base_color)
            
            if door_type == WOODEN_DOOR or door_type == PINE_DOOR:
                panel_color = detail_color
                pygame.draw.rect(surf, panel_color, (8, 8, 24, 24))
                pygame.draw.rect(surf, panel_color, (8, TILE_SIZE + 8, 24, 24))
                pygame.draw.rect(surf, (100, 70, 30) if door_type == WOODEN_DOOR else (60, 45, 25), 
                               (10, 10, 20, 20), 2)
                pygame.draw.rect(surf, (100, 70, 30) if door_type == WOODEN_DOOR else (60, 45, 25), 
                               (10, TILE_SIZE + 10, 20, 20), 2)
                pygame.draw.circle(surf, (100, 70, 30) if door_type == WOODEN_DOOR else (60, 45, 25), 
                                 (30, TILE_SIZE // 2), 3)
            else:
                pygame.draw.circle(surf, detail_color, (10, 10), 3)
                pygame.draw.circle(surf, detail_color, (30, 10), 3)
                pygame.draw.circle(surf, detail_color, (10, TILE_SIZE - 10), 3)
                pygame.draw.circle(surf, detail_color, (30, TILE_SIZE - 10), 3)
                pygame.draw.circle(surf, detail_color, (10, TILE_SIZE + 10), 3)
                pygame.draw.circle(surf, detail_color, (30, TILE_SIZE + 10), 3)
                pygame.draw.circle(surf, detail_color, (10, TILE_SIZE * 2 - 10), 3)
                pygame.draw.circle(surf, detail_color, (30, TILE_SIZE * 2 - 10), 3)
                pygame.draw.circle(surf, (100, 100, 100), (30, TILE_SIZE // 2), 4)
            
            return surf
        except:
            return pygame.Surface((TILE_SIZE, TILE_SIZE * 2))

    def create_fallback_texture(self, b_id, color):
        try:
            if b_id in [WOODEN_DOOR, PINE_DOOR]:
                self.textures[b_id] = self.create_door_texture(b_id, False)
            elif b_id == PINE_WOOD:
                surf = pygame.Surface((TILE_SIZE, TILE_SIZE), pygame.SRCALPHA)
                surf.fill(color)
                for i in range(0, TILE_SIZE, 8):
                    pygame.draw.rect(surf, (60, 45, 30), (i, 0, 2, TILE_SIZE))
                    pygame.draw.rect(surf, (100, 80, 60), (i+2, 5, 4, TILE_SIZE-10))
                self.textures[b_id] = surf
            elif b_id == PINE_PLANK:
                surf = pygame.Surface((TILE_SIZE, TILE_SIZE), pygame.SRCALPHA)
                surf.fill(color)
                for i in range(0, TILE_SIZE, 4):
                    shade = random.randint(60, 80)
                    pygame.draw.line(surf, (shade, shade-10, shade-20), (i, 0), (i, TILE_SIZE), 1)
                for _ in range(3):
                    knot_x = random.randint(5, TILE_SIZE-10)
                    knot_y = random.randint(5, TILE_SIZE-10)
                    pygame.draw.circle(surf, (40, 30, 20), (knot_x, knot_y), 3)
                    pygame.draw.circle(surf, (30, 20, 10), (knot_x, knot_y), 2)
                self.textures[b_id] = surf
            elif b_id == TORCH:
                surf = pygame.Surface((TILE_SIZE // 2, TILE_SIZE), pygame.SRCALPHA)
                pygame.draw.rect(surf, (160, 120, 60), (TILE_SIZE // 4 - 2, TILE_SIZE // 2, 4, TILE_SIZE // 2))
                points = [
                    (TILE_SIZE // 4, TILE_SIZE // 4),
                    (TILE_SIZE // 4 + 6, TILE_SIZE // 2),
                    (TILE_SIZE // 4, TILE_SIZE // 2 + 4),
                    (TILE_SIZE // 4 - 6, TILE_SIZE // 2)
                ]
                pygame.draw.polygon(surf, (255, 100, 0), points)
                pygame.draw.polygon(surf, (255, 200, 0), [
                    (TILE_SIZE // 4, TILE_SIZE // 4 + 2),
                    (TILE_SIZE // 4 + 4, TILE_SIZE // 2 - 2),
                    (TILE_SIZE // 4, TILE_SIZE // 2),
                    (TILE_SIZE // 4 - 4, TILE_SIZE // 2 - 2)
                ])
                self.textures[b_id] = surf
            elif b_id == CRAFTING_TABLE:
                surf = pygame.Surface((TILE_SIZE * 2, TILE_SIZE), pygame.SRCALPHA)
                surf.fill(color + (255,) if len(color) == 3 else color)
                pygame.draw.rect(surf, (0, 0, 0, 50), (0, 0, TILE_SIZE * 2, TILE_SIZE), 1)
                self.textures[b_id] = surf
            elif b_id == FURNACE:
                surf = pygame.Surface((TILE_SIZE, TILE_SIZE * 2), pygame.SRCALPHA)
                surf.fill(color + (255,) if len(color) == 3 else color)
                pygame.draw.rect(surf, (0, 0, 0, 50), (0, 0, TILE_SIZE, TILE_SIZE * 2), 1)
                self.textures[b_id] = surf
            else:
                surf = pygame.Surface((TILE_SIZE, TILE_SIZE), pygame.SRCALPHA)
                if len(color) == 3:
                    surf.fill(color + (255,))
                else:
                    surf.fill(color)
                
                pygame.draw.rect(surf, (0, 0, 0, 50), (0, 0, TILE_SIZE, TILE_SIZE), 1)
                self.textures[b_id] = surf
        except:
            self.textures[b_id] = pygame.Surface((TILE_SIZE, TILE_SIZE))

    def get_biome(self, x):
        v = math.sin((x + self.biome_offset) * 0.005)
        if v > 0.7: return "ASH"       
        if v > 0.2: return "FOREST"    
        if v > -0.3: return "SNOW"     
        return "DESERT"                

    def get_height(self, x):
        h1 = math.sin(x * 0.05 + self.seed) * 5
        h2 = math.sin(x * 0.15 + self.seed * 0.5) * 2
        h3 = math.sin(x * 0.01 + self.seed * 2) * 10
        return int(60 + h1 + h2 + h3)

    def generate_chunk(self, x):
        if x in self.generated_terrain: 
            return
            
        biome = self.get_biome(x)
        ground_y = self.get_height(x)
        
        if self.world_type == "LIMITED" and (x < 0 or x > 300):
            return
            
        for y in range(0, self.world_h):
            if (x, y) in self.world and self.world[(x,y)][0] != EMPTY: 
                continue
                
            if y == ground_y:
                if biome == "FOREST": 
                    self.world[(x, y)] = [GRASS, 0, False]
                elif biome == "SNOW": 
                    self.world[(x, y)] = [SNOW_GRASS, 0, False]
                elif biome == "DESERT": 
                    self.world[(x, y)] = [SAND, 0, False]
                elif biome == "ASH": 
                    self.world[(x, y)] = [ASH, 0, False]
            elif ground_y < y < ground_y + 5:
                self.world[(x, y)] = [SAND if biome == "DESERT" else DIRT, 0, False]
            elif y >= ground_y + 5 and y < self.world_h - 5:
                depth = y - ground_y
                
                if y >= self.world_h - 10:
                    self.world[(x, y)] = [STONE, 0, False]
                    continue
                    
                self.world[(x, y)] = [STONE, 0, False]
            elif y >= self.world_h - 5:
                self.world[(x, y)] = [STONE, 0, False]
            else:
                self.world[(x, y)] = [EMPTY, 0, False]
                
        # Лава в пустыне - реже
        if biome == "DESERT" and random.random() < 0.005:
            self.spawn_lake(x, ground_y, LAVA)
        
        # Вода в других биомах
        elif biome in ["FOREST", "SNOW"] and random.random() < 0.02:
            self.spawn_lake(x, ground_y, WATER)
                    
        if random.random() < 0.15:
            self.generate_cave_worm(x, ground_y + random.randint(10, 50))
        
        if random.random() < 0.1 and ground_y + 100 < self.world_h:
            self.generate_deep_cave(x, ground_y + 100 + random.randint(0, 100))
        
        self.generated_terrain.add(x)
        
        if x not in self.generated_ores:
            self.generate_ores(x, ground_y)

    def generate_ores(self, x, ground_y):
        # Жилы руды: каждый тип руды может "прорасти" в этой колонке с неким
        # шансом, и если это случилось - вырастает компактный кластер (как в
        # Minecraft), а не редкий шум по одной клетке на весь камень. Более
        # ценная руда встречается реже, глубже и меньшими жилами.
        ore_configs = [
            # (руда, мин.глубина, макс.глубина, шанс жилы на колонку, размер жилы)
            (COAL_ORE, 8, 200, 0.35, (5, 12)),
            (IRON_ORE, 20, 250, 0.28, (4, 10)),
            (GOLD_ORE, 60, 320, 0.16, (3, 7)),
        ]
        
        for ore_id, min_depth, max_depth, vein_chance, size_range in ore_configs:
            if random.random() >= vein_chance:
                continue
            
            vein_y = ground_y + random.randint(min_depth, max_depth)
            if not (0 <= vein_y < self.world_h - 10):
                continue
            
            vein_size = random.randint(*size_range)
            # Растим жилу случайным блужданием из центра, а не разбросом по
            # прямоугольнику - получаются более естественные, "живые" формы.
            cx, cy = x, vein_y
            placed = 0
            attempts = 0
            while placed < vein_size and attempts < vein_size * 4:
                attempts += 1
                if (cx, cy) in self.world and self.world[(cx, cy)][0] == STONE:
                    self.world[(cx, cy)] = [ore_id, 0, False]
                    placed += 1
                cx += random.randint(-1, 1)
                cy += random.randint(-1, 1)
        
        self.generated_ores.add(x)

    def spawn_lake(self, x, ground_y, liquid_type):
        """Создаёт озеро/лужу лавы случайного размера и глубины с неровным
        дном - в отличие от старой фиксированной заплатки 5х2, каждое озеро
        получается уникальным."""
        try:
            half_width = random.randint(3, 8)   # итоговая ширина от 6 до 16
            max_depth = random.randint(2, 6)
            
            for dx in range(-half_width, half_width + 1):
                lx = x + dx
                if self.world_type == "LIMITED" and (lx < 0 or lx > 300):
                    continue
                
                # Профиль чаши: глубже в центре, мельче к краям, плюс лёгкий
                # случайный шум, чтобы дно не было идеально симметричным.
                edge_ratio = 1 - (abs(dx) / half_width)
                local_depth = max(1, int(max_depth * edge_ratio + random.uniform(-0.8, 0.8)))
                
                for dy in range(0, local_depth):
                    ly = ground_y + dy
                    if (lx, ly) in self.world:
                        self.world[(lx, ly)] = [liquid_type, MAX_LIQUID_LEVEL, False]
                
                # Помечаем как декорированное, чтобы дерево/кактус не выросли
                # прямо посреди озера при последующем вызове plant_decor.
                self.generated_decor.add(lx)
        except:
            pass

    def generate_cave_worm(self, start_x, start_y):
        cx, cy = float(start_x), float(start_y)
        length = random.randint(15, 25)
        for _ in range(length):
            for dx in range(-1, 2):
                for dy in range(-1, 2):
                    nx = int(cx) + dx
                    ny = int(cy) + dy
                    if self.world_type == "LIMITED" and (nx < 0 or nx > 300):
                        continue
                    if 0 <= ny < self.world_h:
                        self.world[(nx, ny)] = [EMPTY, 0, False]
            cx += random.uniform(-1.5, 1.5)
            cy += random.uniform(-0.5, 1.2)
            if cy > self.world_h - 5: 
                break
            if cy < 45: 
                cy = 45

    def generate_deep_cave(self, start_x, start_y):
        cx, cy = float(start_x), float(start_y)
        length = random.randint(30, 50)
        size_variation = random.uniform(1.0, 4.0)
        
        for i in range(length):
            cave_size = int(3 + size_variation * math.sin(i * 0.2))
            for dx in range(-cave_size, cave_size + 1):
                for dy in range(-cave_size, cave_size + 1):
                    dist = math.sqrt(dx*dx + dy*dy)
                    if dist < cave_size:
                        nx = int(cx) + dx
                        ny = int(cy) + dy
                        if self.world_type == "LIMITED" and (nx < 0 or nx > 300):
                            continue
                        if 0 <= ny < self.world_h:
                            self.world[(nx, ny)] = [EMPTY, 0, False]
            
            if random.random() < 0.3:
                for _ in range(random.randint(1, 5)):
                    sx = int(cx) + random.randint(-cave_size, cave_size)
                    sy = cy + random.randint(-cave_size, cave_size)
                    stal_height = random.randint(1, 6)
                    for h in range(stal_height):
                        if 0 <= sy + h < self.world_h and (sx, int(sy + h)) in self.world:
                            self.world[(sx, int(sy + h))] = [STONE, 0, False]
            
            cx += random.uniform(-2.0, 2.0)
            cy += random.uniform(-1.0, 1.5)
            
            if cy > self.world_h - 20:
                cy = self.world_h - 20
            if cy < start_y - 100:
                cy = start_y - 100

    def spawn_igloo(self, x, ground_y):
        """Создает аккуратное иглу с чётким куполом и входом"""
        try:
            radius = 5
            base_y = ground_y  # уровень земли, на котором стоит иглу
            
            # Купол: полукруг (только верхняя половина сферы), стенка одной клетки толщиной,
            # без "рваных" краёв - используем чёткую окружность вместо 3D-дистанции.
            wall_thickness = 1.4
            for dx in range(-radius - 1, radius + 2):
                for dy in range(-radius - 1, 1):  # только верх (полусфера) + пол на уровне 0
                    dist = math.sqrt(dx * dx + dy * dy)
                    if radius - wall_thickness <= dist <= radius:
                        bx = x + dx
                        by = base_y + dy
                        if self.world_type == "LIMITED" and (bx < 0 or bx > 300):
                            continue
                        self.world[(bx, by)] = [SNOW_GRASS, 0, False]
            
            # Внутренняя часть иглу - расчищаем пустоту под куполом
            for dx in range(-radius + 1, radius):
                for dy in range(-radius + 1, 1):
                    dist = math.sqrt(dx * dx + dy * dy)
                    if dist < radius - wall_thickness:
                        bx = x + dx
                        by = base_y + dy
                        if self.world_type == "LIMITED" and (bx < 0 or bx > 300):
                            continue
                        self.world[(bx, by)] = [EMPTY, 0, False]
            
            # Пол иглу
            for dx in range(-radius + 2, radius - 1):
                bx = x + dx
                by = base_y
                if self.world_type == "LIMITED" and (bx < 0 or bx > 300):
                    continue
                self.world[(bx, by)] = [SNOW_GRASS, 0, False]
            
            # Вход - короткий туннель наружу через стену, без двери (по просьбе)
            tunnel_y = base_y - 1
            for dx in range(radius - 1, radius + 3):
                bx = x + dx
                self.world[(bx, tunnel_y)] = [EMPTY, 0, False]
                self.world[(bx, tunnel_y - 1)] = [SNOW_GRASS, 0, False]
            
            # Обстановка внутри
            self.world[(x - 1, base_y - 1)] = [CRAFTING_TABLE, 0, False]
            self.world[(x + 1, base_y - 1)] = [FURNACE, 0, False]
            self.furnaces[(x + 1, base_y - 1)] = Furnace(x + 1, base_y - 1)
            
            self.world[(x, base_y - 2)] = [TORCH, 0, False]
            self.torches[(x, base_y - 2)] = Torch(x, base_y - 2)
        except:
            pass

    def plant_decor(self, x):
        if x in self.generated_decor: 
            return
            
        biome = self.get_biome(x)
        ground_y = self.get_height(x)
        
        if self.world_type == "LIMITED" and (x < 0 or x > 300):
            self.generated_decor.add(x)
            return
        
        try:
            if biome == "FOREST" and random.random() < 0.06:
                self.generate_beautiful_tree(x, ground_y, "FOREST")
            elif biome == "SNOW" and random.random() < 0.05:
                self.generate_beautiful_tree(x, ground_y, "SNOW")
            elif biome == "DESERT" and random.random() < 0.03:
                h = random.randint(3, 4)
                for i in range(h): 
                    bx = x
                    if self.world_type == "LIMITED" and (bx < 0 or bx > 300):
                        continue
                    self.world[(bx, ground_y-1-i)] = [CACTUS, 0, False]
            elif biome == "ASH" and random.random() < 0.01:
                for vx in range(x-5, x+6):
                    if self.world_type == "LIMITED" and (vx < 0 or vx > 300):
                        continue
                    dist = abs(x - vx)
                    for vy in range(ground_y - (5-dist), ground_y + 1):
                        self.world[(vx, vy)] = [STONE, 0, False]
                self.world[(x, ground_y-5)] = [LAVA, MAX_LIQUID_LEVEL, False]
            
            if biome == "SNOW" and random.random() < 0.005:
                self.spawn_igloo(x, ground_y)
                for area_x in range(x-12, x+13): 
                    self.generated_decor.add(area_x)
                return
        except:
            pass
            
        self.generated_decor.add(x)

    def generate_beautiful_tree(self, x, ground_y, biome_type):
        try:
            if biome_type == "FOREST":
                height = random.randint(7, 10)
                leaf_radius = 4
                
                for i in range(height):
                    bx = x
                    by = ground_y - 1 - i
                    if self.world_type == "LIMITED" and (bx < 0 or bx > 300):
                        continue
                    self.world[(bx, by)] = [WOOD, 0, False]
                
                for layer in range(4):
                    layer_y = ground_y - height + layer - 1
                    layer_radius = leaf_radius - layer
                    
                    for dx in range(-layer_radius, layer_radius + 1):
                        for dz in range(-1, 2):
                            for dy in range(-2, 2):
                                if abs(dx) + abs(dy) <= layer_radius:
                                    lx = x + dx
                                    ly = layer_y + dy
                                    if self.world_type == "LIMITED" and (lx < 0 or lx > 300):
                                        continue
                                    if ly > ground_y - height - 2 and ly < ground_y:
                                        if random.random() < 0.8:
                                            if (lx, ly) not in self.world or self.world[(lx, ly)][0] == EMPTY:
                                                self.world[(lx, ly)] = [LEAVES, 0, False]
                
                top_y = ground_y - height - 2
                for dx in range(-2, 3):
                    for dy in range(-2, 3):
                        if abs(dx) + abs(dy) <= 2:
                            lx = x + dx
                            ly = top_y + dy
                            if self.world_type == "LIMITED" and (lx < 0 or lx > 300):
                                continue
                            if (lx, ly) not in self.world or self.world[(lx, ly)][0] == EMPTY:
                                self.world[(lx, ly)] = [LEAVES, 0, False]
            
            elif biome_type == "SNOW":
                height = random.randint(9, 13)
                
                for i in range(height):
                    bx = x
                    by = ground_y - 1 - i
                    if self.world_type == "LIMITED" and (bx < 0 or bx > 300):
                        continue
                    self.world[(bx, by)] = [PINE_LOG, 0, False]
                
                for layer in range(6):
                    layer_y = ground_y - height + layer * 2 - 1
                    layer_radius = 4 - layer // 2
                    
                    for dx in range(-layer_radius, layer_radius + 1):
                        for dz in range(-1, 2):
                            for dy in range(-2, 3):
                                dist = math.sqrt(dx*dx + dy*dy)
                                if dist <= layer_radius + 0.5:
                                    lx = x + dx
                                    ly = layer_y + dy
                                    if self.world_type == "LIMITED" and (lx < 0 or lx > 300):
                                        continue
                                    if ly > ground_y - height - 3 and ly < ground_y - 1:
                                        if random.random() < 0.7:
                                            if (lx, ly) not in self.world or self.world[(lx, ly)][0] == EMPTY:
                                                self.world[(lx, ly)] = [PINE_LEAVES, 0, False]
                
                top_y = ground_y - height - 3
                for dx in range(-2, 3):
                    for dy in range(-2, 3):
                        if abs(dx) + abs(dy) <= 2:
                            lx = x + dx
                            ly = top_y + dy
                            if self.world_type == "LIMITED" and (lx < 0 or lx > 300):
                                continue
                            if (lx, ly) not in self.world or self.world[(lx, ly)][0] == EMPTY:
                                self.world[(lx, ly)] = [PINE_LEAVES, 0, False]
        except:
            pass

    def update_infinite_world(self):
        try:
            px = int(self.player_rect.centerx // TILE_SIZE)
            for x in range(px - UPDATE_DISTANCE, px + UPDATE_DISTANCE):
                self.generate_chunk(x)
            for x in range(px - RENDER_DISTANCE, px + RENDER_DISTANCE):
                self.plant_decor(x)
        except:
            pass

    def update_ash_particles(self):
        try:
            px = int(self.player_rect.centerx // TILE_SIZE)
            if self.get_biome(px) == "ASH" and random.random() < 0.3:
                self.ash_particles.append([random.randint(0, WIDTH), -10, random.uniform(-1, 1), random.uniform(2, 4)])
            for p in self.ash_particles[:]:
                p[0] += p[2]
                p[1] += p[3]
                if p[1] > HEIGHT: 
                    self.ash_particles.remove(p)
        except:
            pass

    def update_physics(self):
        try:
            self.timer += 1
            if self.timer % 5 != 0: 
                return
            
            px = int(self.player_rect.centerx // TILE_SIZE)
            
            # Периодически (не каждый тик) досканируем видимую+ближнюю область
            # на предмет новых активных клеток (например игрок только что
            # телепортировался/загрузил чанк с водой/пепел с песком, которые
            # мы ещё не отслеживаем). Ограничено кулдауном по времени, а не
            # только по смене позиции - иначе при ходьбе px меняется почти
            # каждый кадр и рескан по всей world_h происходил бы так же
            # часто, как и раньше.
            current_time = time.time()
            needs_rescan = (self.last_physics_rescan_x is None or
                             abs(px - self.last_physics_rescan_x) > UPDATE_DISTANCE // 2 or
                             current_time - self.last_physics_rescan_time > 2.0)
            if needs_rescan:
                self.last_physics_rescan_x = px
                self.last_physics_rescan_time = current_time
                for x in range(px - UPDATE_DISTANCE, px + UPDATE_DISTANCE):
                    for y in range(0, self.world_h):
                        block = self.world.get((x, y))
                        if block is not None and block[0] in (SAND, ASH, WATER, LAVA):
                            self.active_physics_tiles.add((x, y))
            
            if not self.active_physics_tiles:
                return
            
            # Обрабатываем только реально активные клетки, а не весь мир.
            # Сортировка снизу вверх сохраняет прежнее поведение падения
            # (нижние клетки двигаются первыми, освобождая место верхним).
            tiles_to_process = sorted(self.active_physics_tiles, key=lambda pos: -pos[1])
            next_active = set()
            
            for (x, y) in tiles_to_process:
                block = self.world.get((x, y))
                if block is None:
                    continue
                b_id, lvl, is_f = block
                
                if b_id in (SAND, ASH):
                    if self.world.get((x, y+1), [EMPTY])[0] == EMPTY:
                        self.world[(x, y+1)], self.world[(x, y)] = [b_id, 0, False], [EMPTY, 0, False]
                        next_active.add((x, y+1))
                    else:
                        next_active.add((x, y))
                
                elif b_id in (WATER, LAVA):
                    below = self.world.get((x, y+1), [EMPTY])[0]
                    if below in (EMPTY, WATER, LAVA):
                        if below == EMPTY:
                            self.world[(x, y+1)] = [b_id, MAX_LIQUID_LEVEL, True]
                            next_active.add((x, y+1))
                        next_active.add((x, y))
                        continue
                    
                    if lvl > 0:
                        for dx in [-1, 1]:
                            if (x + dx) not in self.generated_terrain:
                                continue
                            if self.world.get((x + dx, y), [EMPTY])[0] == EMPTY:
                                self.world[(x + dx, y)] = [b_id, lvl - 1, True]
                                next_active.add((x + dx, y))
                        next_active.add((x, y))
            
            self.active_physics_tiles = next_active
        except:
            pass

    def add_to_inventory_slot(self, item_id, count=1):
        if item_id == EMPTY or item_id == WATER or item_id == LAVA or count <= 0:
            return False
            
        try:
            for i in range(self.hotbar_slots):
                if self.hotbar[i] == item_id:
                    if self.hotbar_counts[i] + count <= 64:
                        self.hotbar_counts[i] += count
                        return True
                elif self.hotbar[i] is None:
                    self.hotbar[i] = item_id
                    self.hotbar_counts[i] = count
                    return True
            
            for i in range(self.inventory_slots):
                if self.inventory[i] == item_id:
                    if self.inventory_counts[i] + count <= 64:
                        self.inventory_counts[i] += count
                        return True
                elif self.inventory[i] is None:
                    self.inventory[i] = item_id
                    self.inventory_counts[i] = count
                    return True
        except:
            pass
        
        return False

    def remove_from_inventory_slot(self, item_id, count=1):
        if count <= 0:
            return False
            
        try:
            for i in range(self.hotbar_slots):
                if self.hotbar[i] == item_id and self.hotbar_counts[i] >= count:
                    self.hotbar_counts[i] -= count
                    if self.hotbar_counts[i] == 0:
                        self.hotbar[i] = None
                    return True
            
            for i in range(self.inventory_slots):
                if self.inventory[i] == item_id and self.inventory_counts[i] >= count:
                    self.inventory_counts[i] -= count
                    if self.inventory_counts[i] == 0:
                        self.inventory[i] = None
                    return True
        except:
            pass
        
        return False

    def get_selected_item(self):
        try:
            if 0 <= self.selected_slot < self.hotbar_slots:
                return self.hotbar[self.selected_slot]
        except:
            pass
        return None

    def get_selected_item_count(self):
        try:
            if 0 <= self.selected_slot < self.hotbar_slots:
                return self.hotbar_counts[self.selected_slot]
        except:
            pass
        return 0

    def get_item_count_in_inventory(self, item_id):
        total = 0
        
        try:
            for i in range(self.hotbar_slots):
                if self.hotbar[i] == item_id:
                    total += self.hotbar_counts[i]
            
            for i in range(self.inventory_slots):
                if self.inventory[i] == item_id:
                    total += self.inventory_counts[i]
        except:
            pass
        
        return total

    def start_dragging(self, item_id, count, from_type, from_index):
        self.dragging_item = item_id
        self.dragging_count = count
        self.dragging_from = (from_type, from_index)

    def stop_dragging(self, to_type=None, to_index=None):
        if self.dragging_item is None:
            return
            
        try:
            if to_type is not None and to_index is not None:
                from_type, from_index = self.dragging_from
                
                if to_type == from_type and to_index == from_index:
                    # Игрок положил предмет обратно в тот же слот, откуда взял -
                    # ничего не меняется. Без этой проверки код ниже трактует
                    # "то же самое" как "стек с таким же предметом" и прибавляет
                    # количество к уже лежащему там же предмету, а затем стирает
                    # исходный слот - из-за чего предмет исчезал полностью.
                    self.dragging_item = None
                    return
                
                if from_type == 'hotbar':
                    from_slot = self.hotbar[from_index]
                    from_count = self.hotbar_counts[from_index]
                elif from_type == 'inventory':
                    from_slot = self.inventory[from_index]
                    from_count = self.inventory_counts[from_index]
                elif from_type == 'furnace_input':
                    furnace = self.furnaces.get(self.furnace_open)
                    if furnace:
                        from_slot = furnace.input_item
                        from_count = furnace.input_count
                    else:
                        from_slot = None
                        from_count = 0
                elif from_type == 'furnace_fuel':
                    furnace = self.furnaces.get(self.furnace_open)
                    if furnace:
                        from_slot = furnace.fuel_item
                        from_count = furnace.fuel_count
                    else:
                        from_slot = None
                        from_count = 0
                else:
                    from_slot = None
                    from_count = 0
                
                if to_type == 'hotbar':
                    to_slot = self.hotbar[to_index]
                    to_count = self.hotbar_counts[to_index]
                elif to_type == 'inventory':
                    to_slot = self.inventory[to_index]
                    to_count = self.inventory_counts[to_index]
                elif to_type == 'furnace_input':
                    furnace = self.furnaces.get(self.furnace_open)
                    if furnace:
                        to_slot = furnace.input_item
                        to_count = furnace.input_count
                    else:
                        to_slot = None
                        to_count = 0
                elif to_type == 'furnace_fuel':
                    furnace = self.furnaces.get(self.furnace_open)
                    if furnace:
                        to_slot = furnace.fuel_item
                        to_count = furnace.fuel_count
                    else:
                        to_slot = None
                        to_count = 0
                else:
                    to_slot = None
                    to_count = 0
                
                if to_slot is None or to_slot == from_slot:
                    if to_slot is None:
                        self._set_slot(to_type, to_index, from_slot, from_count)
                        self._clear_slot(from_type, from_index)
                    else:
                        max_stack = 64
                        available_space = max_stack - to_count
                        
                        if available_space >= from_count:
                            self._add_to_slot(to_type, to_index, from_count)
                            self._clear_slot(from_type, from_index)
                        else:
                            self._set_slot(to_type, to_index, to_slot, max_stack)
                            remaining = from_count - available_space
                            self._set_slot(from_type, from_index, from_slot, remaining)
                else:
                    self._swap_slots(from_type, from_index, to_type, to_index)
        except:
            pass
        
        self.dragging_item = None
        self.dragging_count = 0
        self.dragging_from = None

    def _set_slot(self, slot_type, index, item_id, count):
        try:
            if slot_type == 'hotbar':
                self.hotbar[index] = item_id
                self.hotbar_counts[index] = count
            elif slot_type == 'inventory':
                self.inventory[index] = item_id
                self.inventory_counts[index] = count
            elif slot_type == 'furnace_input':
                furnace = self.furnaces.get(self.furnace_open)
                if furnace:
                    furnace.input_item = item_id
                    furnace.input_count = count
            elif slot_type == 'furnace_fuel':
                furnace = self.furnaces.get(self.furnace_open)
                if furnace:
                    furnace.fuel_item = item_id
                    furnace.fuel_count = count
        except:
            pass

    def _add_to_slot(self, slot_type, index, amount):
        try:
            if slot_type == 'hotbar':
                self.hotbar_counts[index] += amount
            elif slot_type == 'inventory':
                self.inventory_counts[index] += amount
            elif slot_type == 'furnace_input':
                furnace = self.furnaces.get(self.furnace_open)
                if furnace:
                    furnace.input_count += amount
            elif slot_type == 'furnace_fuel':
                furnace = self.furnaces.get(self.furnace_open)
                if furnace:
                    furnace.fuel_count += amount
        except:
            pass

    def _clear_slot(self, slot_type, index):
        try:
            if slot_type == 'hotbar':
                self.hotbar[index] = None
                self.hotbar_counts[index] = 0
            elif slot_type == 'inventory':
                self.inventory[index] = None
                self.inventory_counts[index] = 0
            elif slot_type == 'furnace_input':
                furnace = self.furnaces.get(self.furnace_open)
                if furnace:
                    furnace.input_item = None
                    furnace.input_count = 0
            elif slot_type == 'furnace_fuel':
                furnace = self.furnaces.get(self.furnace_open)
                if furnace:
                    furnace.fuel_item = None
                    furnace.fuel_count = 0
        except:
            pass

    def _swap_slots(self, from_type, from_index, to_type, to_index):
        try:
            if from_type == 'hotbar':
                from_item = self.hotbar[from_index]
                from_count = self.hotbar_counts[from_index]
            elif from_type == 'inventory':
                from_item = self.inventory[from_index]
                from_count = self.inventory_counts[from_index]
            elif from_type == 'furnace_input':
                furnace = self.furnaces.get(self.furnace_open)
                from_item = furnace.input_item if furnace else None
                from_count = furnace.input_count if furnace else 0
            elif from_type == 'furnace_fuel':
                furnace = self.furnaces.get(self.furnace_open)
                from_item = furnace.fuel_item if furnace else None
                from_count = furnace.fuel_count if furnace else 0
            else:
                from_item = None
                from_count = 0
            
            if to_type == 'hotbar':
                to_item = self.hotbar[to_index]
                to_count = self.hotbar_counts[to_index]
            elif to_type == 'inventory':
                to_item = self.inventory[to_index]
                to_count = self.inventory_counts[to_index]
            elif to_type == 'furnace_input':
                furnace = self.furnaces.get(self.furnace_open)
                to_item = furnace.input_item if furnace else None
                to_count = furnace.input_count if furnace else 0
            elif to_type == 'furnace_fuel':
                furnace = self.furnaces.get(self.furnace_open)
                to_item = furnace.fuel_item if furnace else None
                to_count = furnace.fuel_count if furnace else 0
            else:
                to_item = None
                to_count = 0
            
            self._set_slot(from_type, from_index, to_item, to_count)
            self._set_slot(to_type, to_index, from_item, from_count)
        except:
            pass

    def draw_dragging_item(self):
        if self.dragging_item is not None and self.dragging_item in self.textures:
            try:
                mx, my = pygame.mouse.get_pos()
                
                icon = pygame.transform.scale(self.textures[self.dragging_item], (32, 32))
                self.screen.blit(icon, (mx - 16, my - 16))
                
                if self.dragging_count > 1:
                    font = pygame.font.SysFont("Arial", 16, bold=True)
                    count_text = font.render(str(self.dragging_count), True, (255, 255, 255))
                    self.screen.blit(count_text, (mx + 10, my + 10))
            except:
                pass

    def can_craft(self, recipe):
        try:
            for item_id, count in recipe.items():
                if self.get_item_count_in_inventory(item_id) < count:
                    return False
            return True
        except:
            return False

    def craft_item(self, recipe_key, in_crafting_table=False):
        recipes = self.crafting_table_recipes if in_crafting_table else self.inventory_recipes
        
        try:
            for recipe in recipes:
                key, name, required, result, count, description = recipe
                
                if key == recipe_key:
                    if not self.can_craft(required):
                        return False
                    
                    for item_id, amount in required.items():
                        self.remove_from_inventory_slot(item_id, amount)
                    
                    self.add_to_inventory_slot(result, count)
                    return True
        except:
            pass
        
        return False

    def update_dropped_items(self):
        items_to_remove = []
        
        try:
            for i, item in enumerate(self.dropped_items):
                if not item.update(self.world):
                    items_to_remove.append(i)
                    continue
                
                item_rect = item.get_rect()
                player_rect = pygame.Rect(
                    self.player_rect.x,
                    self.player_rect.y,
                    self.player_rect.width,
                    self.player_rect.height
                )
                
                if item_rect.colliderect(player_rect):
                    if self.add_to_inventory_slot(item.item_id, item.count):
                        try:
                            self.play_collect_sound()
                        except:
                            pass
                        items_to_remove.append(i)
        except:
            pass
    
        for i in reversed(items_to_remove):
            self.dropped_items.pop(i)

    def drop_item_from_inventory(self):
        selected_item = self.get_selected_item()
        count = self.get_selected_item_count()
        
        if selected_item is not None and count > 0:
            try:
                direction = 1 if self.player_facing == "right" else -1
                drop_x = self.player_rect.centerx + direction * 40
                drop_y = self.player_rect.centery
                
                drop_count = min(count, 5)
                for i in range(drop_count):
                    offset_x = random.uniform(-10, 10)
                    offset_y = random.uniform(-5, 5)
                    self.dropped_items.append(DroppedItem(
                        selected_item, 
                        drop_x + offset_x, 
                        drop_y + offset_y, 
                        1
                    ))
                
                self.remove_from_inventory_slot(selected_item, drop_count)
                return True
            except:
                pass
        return False

    def get_mining_multiplier(self, block_id, tool_id):
        if tool_id is None:
            return 1.0
        
        try:
            block_names = {
                STONE: "STONE",
                WOOD: "WOOD",
                PINE_LOG: "PINE_LOG",
                CRAFTING_TABLE: "CRAFTING_TABLE",
                WOODEN_DOOR: "WOODEN_DOOR",
                IRON_DOOR: "IRON_DOOR",
                PINE_DOOR: "PINE_DOOR",
                FURNACE: "FURNACE",
                COAL_ORE: "COAL_ORE",
                IRON_ORE: "IRON_ORE",
                GOLD_ORE: "GOLD_ORE",
                DIAMOND_ORE: "DIAMOND_ORE",
                TORCH: "TORCH"
            }
            
            block_name = block_names.get(block_id)
            if block_name and tool_id in self.tool_multipliers:
                return self.tool_multipliers[tool_id].get(block_name, 1.0)
        except:
            pass
        
        return 1.0

    def start_mining(self, block_x, block_y):
        try:
            if (block_x, block_y) in self.world:
                block_id = self.world[(block_x, block_y)][0]
                if block_id == EMPTY or block_id == WATER or block_id == LAVA:
                    return False
                
                if block_id == STONE:
                    tool_id = self.get_selected_item()
                    if tool_id not in [WOODEN_PICKAXE, STONE_PICKAXE, IRON_PICKAXE, GOLD_PICKAXE, DIAMOND_PICKAXE]:
                        return False
                
                self.mining_target = (block_x, block_y)
                self.mining_start_time = time.time()
                self.mining_progress = 0.0
                self.is_mining = True
                return True
        except:
            pass
        return False

    def update_mining(self):
        if not self.is_mining or self.mining_target is None:
            return
        
        try:
            current_time = time.time()
            elapsed_time = current_time - self.mining_start_time
            
            if (self.mining_target[0], self.mining_target[1]) not in self.world:
                self.stop_mining()
                return
            
            block_id = self.world[self.mining_target][0]
            
            if block_id == EMPTY or block_id == WATER or block_id == LAVA:
                self.stop_mining()
                return
            
            mining_time = self.mining_times.get(block_id, 1.0)
            
            tool_id = self.get_selected_item()
            multiplier = self.get_mining_multiplier(block_id, tool_id)
            mining_time /= multiplier
            
            self.mining_progress = min(elapsed_time / mining_time, 1.0)
            
            if self.mining_progress >= 1.0:
                self.finish_mining()
        except:
            self.stop_mining()
    
    def stop_mining(self):
        self.is_mining = False
        self.mining_target = None
        self.mining_progress = 0.0
    
    def finish_mining(self):
        if self.mining_target is None:
            return
        
        try:
            block_x, block_y = self.mining_target
            if (block_x, block_y) in self.world:
                block_id = self.world[(block_x, block_y)][0]
                
                tool_id = self.get_selected_item()
                
                if block_id == STONE and tool_id not in [WOODEN_PICKAXE, STONE_PICKAXE, IRON_PICKAXE, GOLD_PICKAXE, DIAMOND_PICKAXE]:
                    self.stop_mining()
                    return
                elif block_id == DIAMOND_ORE and tool_id not in [IRON_PICKAXE, GOLD_PICKAXE, DIAMOND_PICKAXE]:
                    self.stop_mining()
                    return
                elif block_id == GOLD_ORE and tool_id not in [IRON_PICKAXE, GOLD_PICKAXE, DIAMOND_PICKAXE]:
                    self.stop_mining()
                    return
                elif block_id == IRON_ORE and tool_id not in [STONE_PICKAXE, IRON_PICKAXE, GOLD_PICKAXE, DIAMOND_PICKAXE]:
                    self.stop_mining()
                    return
                
                if block_id in [WOODEN_DOOR, PINE_DOOR]:
                    if (block_x, block_y) in self.door_states:
                        self.door_states.pop((block_x, block_y), None)
                    self.world.pop((block_x, block_y), None)
                    self.dropped_items.append(DroppedItem(block_id, block_x * TILE_SIZE + TILE_SIZE // 2, block_y * TILE_SIZE + TILE_SIZE // 2))
                
                elif block_id == FURNACE:
                    if (block_x, block_y) in self.furnaces:
                        furnace = self.furnaces[(block_x, block_y)]
                        if furnace.input_item and furnace.input_count > 0:
                            self.dropped_items.append(DroppedItem(
                                furnace.input_item,
                                block_x * TILE_SIZE + TILE_SIZE // 2,
                                block_y * TILE_SIZE + TILE_SIZE // 2,
                                furnace.input_count
                            ))
                        
                        if furnace.fuel_item and furnace.fuel_count > 0:
                            self.dropped_items.append(DroppedItem(
                                furnace.fuel_item,
                                block_x * TILE_SIZE + TILE_SIZE // 2,
                                block_y * TILE_SIZE + TILE_SIZE // 2,
                                furnace.fuel_count
                            ))
                        
                        if furnace.output_item and furnace.output_count > 0:
                            self.dropped_items.append(DroppedItem(
                                furnace.output_item,
                                block_x * TILE_SIZE + TILE_SIZE // 2,
                                block_y * TILE_SIZE + TILE_SIZE // 2,
                                furnace.output_count
                            ))
                        
                        self.furnaces.pop((block_x, block_y), None)
                    
                    self.world.pop((block_x, block_y), None)
                    self.dropped_items.append(DroppedItem(FURNACE, block_x * TILE_SIZE + TILE_SIZE // 2, block_y * TILE_SIZE + TILE_SIZE // 2))
                
                elif block_id == TORCH:
                    if (block_x, block_y) in self.torches:
                        self.torches.pop((block_x, block_y), None)
                    self.world.pop((block_x, block_y), None)
                    self.dropped_items.append(DroppedItem(TORCH, block_x * TILE_SIZE + TILE_SIZE // 2, block_y * TILE_SIZE + TILE_SIZE // 2))
                
                else:
                    self.world[(block_x, block_y)] = [EMPTY, 0, False]
                    
                    if block_id not in [EMPTY, WATER, LAVA]:
                        drop_item = COAL if block_id == COAL_ORE else block_id
                        self.dropped_items.append(DroppedItem(drop_item, block_x * TILE_SIZE + TILE_SIZE // 2, block_y * TILE_SIZE + TILE_SIZE // 2))
                    
                    # Пробуждаем соседние клетки для физики: то, что было
                    # выкопано, могло держать песок/пепел сверху или
                    # блокировать жидкость сбоку/сверху - без этого пришлось
                    # бы ждать следующего периодического рескана (до ~2 сек).
                    for nx, ny in [(block_x, block_y - 1), (block_x, block_y + 1), (block_x - 1, block_y), (block_x + 1, block_y)]:
                        neighbor = self.world.get((nx, ny))
                        if neighbor is not None and neighbor[0] in (SAND, ASH, WATER, LAVA):
                            self.active_physics_tiles.add((nx, ny))
        except:
            pass
        
        self.stop_mining()

    def toggle_door(self, door_x, door_y):
        if (door_x, door_y) in self.door_states:
            # Переключаем состояние двери
            self.door_states[(door_x, door_y)][1] = not self.door_states[(door_x, door_y)][1]
            
            # Обновляем блок в мире с правильным ID для текстуры (ID остается тем же)
            door_id = self.door_states[(door_x, door_y)][0]
            self.world[(door_x, door_y)] = [door_id, 0, False]

    def can_place_door(self, x, y):
        if self.get_multitile_origin(x, y) is not None:
            return False
        try:
            if (x, y+1) not in self.world:
                return False
            
            bottom_block = self.world[(x, y+1)][0]
            if bottom_block in self.non_solid_blocks:
                return False
            
            if (x, y) in self.world and self.world[(x, y)][0] != EMPTY:
                return False
            
            if (x, y-1) in self.world and self.world[(x, y-1)][0] != EMPTY:
                return False
        except:
            return False
        
        return True

    def can_place_torch(self, x, y):
        if self.get_multitile_origin(x, y) is not None:
            return False
        try:
            if (x, y+1) not in self.world:
                return False
            
            block_below = self.world[(x, y+1)][0]
            if block_below in self.non_solid_blocks or block_below == TORCH:
                return False
            
            if (x, y) in self.world and self.world[(x, y)][0] != EMPTY:
                return False
        except:
            return False
        
        return True

    def dry_up_disconnected_liquid(self, x, y):
        """Вызывается после того, как твёрдый блок замещает жидкость в (x, y),
        то есть потенциальный источник исчез. Проверяет каждую соседнюю
        клетку с жидкостью того же типа: если связная область (поток) вокруг
        неё больше не содержит НИ ОДНОГО настоящего источника (is_source ==
        False), вся эта область высыхает (становится EMPTY) - как в
        Minecraft, где перекрытие источника осушает утёкшие от него потоки."""
        try:
            for liquid_type in (WATER, LAVA):
                for start_dx, start_dy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                    start = (x + start_dx, y + start_dy)
                    if start not in self.world or self.world[start][0] != liquid_type:
                        continue
                    
                    visited = set()
                    queue = [start]
                    visited.add(start)
                    has_source = False
                    
                    while queue:
                        cx, cy = queue.pop()
                        block = self.world.get((cx, cy))
                        if block is None or block[0] != liquid_type:
                            continue
                        if block[2] is False:
                            has_source = True
                        for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                            npos = (cx + dx, cy + dy)
                            if npos in visited:
                                continue
                            nblock = self.world.get(npos)
                            if nblock is not None and nblock[0] == liquid_type:
                                visited.add(npos)
                                queue.append(npos)
                    
                    if not has_source:
                        for pos in visited:
                            self.world[pos] = [EMPTY, 0, False]
        except:
            pass

    def get_multitile_origin(self, x, y):
        """Верстак занимает 2x1 (клетка + справа), печка 1x2 (клетка + сверху).
        В мире хранится только якорная клетка; по любой из занятых клеток
        возвращает якорь (ox, oy), иначе None."""
        b = self.world.get((x, y))
        if b is not None and b[0] in (CRAFTING_TABLE, FURNACE):
            return (x, y)
        b = self.world.get((x - 1, y))
        if b is not None and b[0] == CRAFTING_TABLE:
            return (x - 1, y)
        b = self.world.get((x, y + 1))
        if b is not None and b[0] == FURNACE:
            return (x, y + 1)
        return None

    def get_multitile_rect(self, ox, oy, block_id):
        if block_id == CRAFTING_TABLE:
            return pygame.Rect(ox * TILE_SIZE, oy * TILE_SIZE, TILE_SIZE * 2, TILE_SIZE)
        return pygame.Rect(ox * TILE_SIZE, (oy - 1) * TILE_SIZE, TILE_SIZE, TILE_SIZE * 2)

    def can_place_block(self, x, y, block_id=None):
        """Проверяет можно ли поставить блок: только в воздух, воду или лаву -
        не поверх уже существующего твёрдого/декоративного блока.
        Для верстака/печки проверяется и вторая клетка."""
        if self.get_multitile_origin(x, y) is not None:
            return False
        if block_id == CRAFTING_TABLE:
            if not self.can_place_block(x + 1, y):
                return False
        elif block_id == FURNACE:
            if not self.can_place_block(x, y - 1):
                return False
        existing = self.world.get((x, y))
        if existing is None:
            return True
        block_id = existing[0]
        return block_id == EMPTY or block_id == WATER or block_id == LAVA

    def place_door(self, x, y, door_id):
        if not self.can_place_door(x, y):
            return False
        
        self.world[(x, y)] = [door_id, 0, False]
        self.door_states[(x, y)] = [door_id, False]
        
        return True

    def place_torch(self, x, y):
        if not self.can_place_torch(x, y):
            return False
        
        self.world[(x, y)] = [TORCH, 0, False]
        self.torches[(x, y)] = Torch(x, y)
        
        return True

    def update_furnaces(self):
        try:
            for pos, furnace in list(self.furnaces.items()):
                furnace.update()
                
                if pos in self.world:
                    block_id = self.world[pos][0]
                    if block_id != FURNACE:
                        if furnace.input_item and furnace.input_count > 0:
                            self.dropped_items.append(DroppedItem(
                                furnace.input_item,
                                pos[0] * TILE_SIZE + TILE_SIZE // 2,
                                pos[1] * TILE_SIZE + TILE_SIZE // 2,
                                furnace.input_count
                            ))
                        
                        if furnace.fuel_item and furnace.fuel_count > 0:
                            self.dropped_items.append(DroppedItem(
                                furnace.fuel_item,
                                pos[0] * TILE_SIZE + TILE_SIZE // 2,
                                pos[1] * TILE_SIZE + TILE_SIZE // 2,
                                furnace.fuel_count
                            ))
                        
                        if furnace.output_item and furnace.output_count > 0:
                            self.dropped_items.append(DroppedItem(
                                furnace.output_item,
                                pos[0] * TILE_SIZE + TILE_SIZE // 2,
                                pos[1] * TILE_SIZE + TILE_SIZE // 2,
                                furnace.output_count
                            ))
                        
                        self.furnaces.pop(pos, None)
        except:
            pass

    def draw_furnace_ui(self, furnace):
        try:
            overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            overlay.fill((0, 0, 0, 210))
            self.screen.blit(overlay, (0, 0))
            
            ui_width, ui_height = min(760, int(WIDTH * 0.95)), min(560, int(HEIGHT * 0.9))
            ui_x, ui_y = (WIDTH - ui_width) // 2, (HEIGHT - ui_height) // 2
            ui_rect = pygame.Rect(ui_x, ui_y, ui_width, ui_height)
            mouse_pos = pygame.mouse.get_pos()
            
            self.draw_ui_panel(ui_rect, "ПЕЧКА")
            close_rect = pygame.Rect(ui_rect.right - 46, ui_rect.y + 12, 34, 34)
            self.draw_ui_close_button(close_rect)
            self.furnace_close_btn = close_rect
            
            slot_size = 64
            left_x = ui_x + 48
            left_y = ui_y + 110
            
            input_rect = pygame.Rect(left_x, left_y, slot_size, slot_size)
            self.furnace_input_rect = input_rect
            label = self.small_font.render("СЫРЬЁ", True, self.UI_TEXT_DIM)
            self.screen.blit(label, (input_rect.centerx - label.get_width()//2, input_rect.y - 22))
            self.draw_ui_slot(input_rect, furnace.input_item, furnace.input_count, input_rect.collidepoint(mouse_pos))
            
            fuel_rect = pygame.Rect(left_x, left_y + slot_size + 24, slot_size, slot_size)
            self.furnace_fuel_rect = fuel_rect
            fuel_label = self.small_font.render("ТОПЛИВО", True, self.UI_TEXT_DIM)
            self.screen.blit(fuel_label, (fuel_rect.centerx - fuel_label.get_width()//2, fuel_rect.y - 22))
            self.draw_ui_slot(fuel_rect, furnace.fuel_item, furnace.fuel_count, fuel_rect.collidepoint(mouse_pos))
            
            # Индикатор горения между сырьём/топливом и стрелкой прогресса
            flame_center = (left_x + slot_size + 34, (input_rect.centery + fuel_rect.centery) // 2)
            flame_color = (255, 150 + int(40 * math.sin(self.timer * 0.3)), 30) if furnace.is_burning else (70, 70, 70)
            pygame.draw.circle(self.screen, flame_color, flame_center, 14)
            pygame.draw.circle(self.screen, self.UI_BORDER, flame_center, 14, 2)
            
            # Стрелка/прогресс-бар переплавки
            arrow_x = flame_center[0] + 26
            arrow_y = input_rect.centery + (fuel_rect.centery - input_rect.centery)//2 - 10
            progress_rect = pygame.Rect(arrow_x, arrow_y, 90, 20)
            pygame.draw.rect(self.screen, (18, 19, 24), progress_rect, border_radius=6)
            if furnace.is_burning and furnace.max_progress > 0:
                fill_width = int(progress_rect.width * (furnace.progress / furnace.max_progress))
                if fill_width > 0:
                    pygame.draw.rect(self.screen, self.UI_ACCENT, (progress_rect.x, progress_rect.y, fill_width, progress_rect.height), border_radius=6)
            pygame.draw.rect(self.screen, self.UI_BORDER, progress_rect, 2, border_radius=6)
            arrow_text = self.small_font.render("→", True, self.UI_TEXT_DIM)
            self.screen.blit(arrow_text, (progress_rect.centerx - arrow_text.get_width()//2, progress_rect.bottom + 4))
            
            output_rect = pygame.Rect(arrow_x + 120, left_y + (slot_size + 24)//2, slot_size, slot_size)
            self.furnace_output_rect = output_rect
            out_label = self.small_font.render("РЕЗУЛЬТАТ", True, self.UI_TEXT_DIM)
            self.screen.blit(out_label, (output_rect.centerx - out_label.get_width()//2, output_rect.y - 22))
            self.draw_ui_slot(output_rect, furnace.output_item, furnace.output_count, output_rect.collidepoint(mouse_pos))
            
            status_y = left_y + slot_size * 2 + 60
            if furnace.is_burning:
                status_text = self.small_font.render("Горит", True, self.UI_ACCENT)
            else:
                status_text = self.small_font.render("Не горит — добавьте топливо", True, self.UI_TEXT_DIM)
            self.screen.blit(status_text, (left_x, status_y))
            
            # Разделитель между зоной печки и инвентарём игрока
            divider_x = ui_x + 330
            pygame.draw.line(self.screen, self.UI_BORDER, (divider_x, ui_y + 84), (divider_x, ui_rect.bottom - 60), 2)
            
            right_x = divider_x + 24
            right_y = ui_y + 110
            
            inv_title = self.small_font.render("ВАШ ИНВЕНТАРЬ", True, self.UI_TEXT_DIM)
            self.screen.blit(inv_title, (right_x, right_y - 22))
            
            slot_gap = 8
            self.furnace_hotbar_slot_rects = []
            for i in range(self.hotbar_slots):
                slot_rect = pygame.Rect(right_x + i * (slot_size + slot_gap), right_y, slot_size, slot_size)
                self.furnace_hotbar_slot_rects.append(slot_rect)
                self.draw_ui_slot(slot_rect, self.hotbar[i], self.hotbar_counts[i], slot_rect.collidepoint(mouse_pos))
            
            furnace_inv_y = right_y + slot_size + 20
            self.furnace_inventory_slot_rects = []
            for i in range(self.inventory_slots):
                row, col = i // 9, i % 9
                slot_rect = pygame.Rect(right_x + col * (slot_size + slot_gap), furnace_inv_y + row * (slot_size + slot_gap), slot_size, slot_size)
                self.furnace_inventory_slot_rects.append(slot_rect)
                self.draw_ui_slot(slot_rect, self.inventory[i], self.inventory_counts[i], slot_rect.collidepoint(mouse_pos))
            
            hints_y = ui_rect.bottom - 30
            hint = self.small_font.render("ЛКМ — переложить  ·  ПКМ — половину  ·  Перетащите предметы в печку", True, self.UI_TEXT_DIM)
            self.screen.blit(hint, (ui_rect.centerx - hint.get_width()//2, hints_y))
        except:
            pass

    def draw_pause_menu(self):
        try:
            overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            overlay.fill((0, 0, 0, 210))
            self.screen.blit(overlay, (0, 0))
            
            ui_width, ui_height = min(440, int(WIDTH * 0.9)), min(360, int(HEIGHT * 0.85))
            ui_x, ui_y = (WIDTH - ui_width) // 2, (HEIGHT - ui_height) // 2
            ui_rect = pygame.Rect(ui_x, ui_y, ui_width, ui_height)
            
            self.draw_ui_panel(ui_rect, "ПАУЗА")
            
            btn_width, btn_height = 340, 56
            btn_x = ui_rect.centerx - btn_width // 2
            btn_gap = 16
            
            resume_btn = pygame.Rect(btn_x, ui_y + 100, btn_width, btn_height)
            settings_btn = pygame.Rect(btn_x, resume_btn.bottom + btn_gap, btn_width, btn_height)
            exit_btn = pygame.Rect(btn_x, settings_btn.bottom + btn_gap, btn_width, btn_height)
            
            self.draw_ui_button(resume_btn, "Вернуться в игру")
            self.draw_ui_button(settings_btn, "Настройки")
            self.draw_ui_button(exit_btn, "Выйти в меню")
            
            self.pause_resume_btn = resume_btn
            self.pause_settings_btn = settings_btn
            self.pause_exit_btn = exit_btn
        except:
            pass

    def get_settings_layout(self):
        """Геометрия меню настроек - единая для отрисовки и обработки нажатий."""
        ui_width = min(520, int(WIDTH * 0.94))
        ui_height = min(560, int(HEIGHT * 0.94))
        ui_x, ui_y = (WIDTH - ui_width) // 2, (HEIGHT - ui_height) // 2
        ui_rect = pygame.Rect(ui_x, ui_y, ui_width, ui_height)
        k = ui_height / 560.0
        pad = int(30 * min(1.0, ui_width / 520.0))
        slider_width = ui_width - pad * 2
        slider_x = ui_x + pad
        n = len(self.GRAPHICS_PRESETS)
        gap = 8
        btn_w = (slider_width - gap * (n - 1)) // n
        btn_h = max(34, int(46 * k))
        gfx_y = ui_y + int(104 * k)
        gfx_btns = [pygame.Rect(slider_x + i * (btn_w + gap), gfx_y, btn_w, btn_h) for i in range(n)]
        sliders_y = {
            'music': ui_y + int(236 * k),
            'sound': ui_y + int(306 * k),
            'view_x': ui_y + int(376 * k),
            'view_y': ui_y + int(446 * k),
        }
        back_btn = pygame.Rect(ui_rect.centerx - 140, ui_y + ui_height - int(58 * k) - 6, 280, max(38, int(48 * k)))
        return {'ui_rect': ui_rect, 'slider_x': slider_x, 'slider_width': slider_width,
                'gfx_btns': gfx_btns, 'gfx_label_y': gfx_y - 26, 'sliders_y': sliders_y,
                'back_btn': back_btn}

    def get_slider_ratio(self, name):
        if name == 'music':
            return self.music_volume
        if name == 'sound':
            return self.sound_volume
        if name == 'view_x':
            return (self.view_dist_x - self.VIEW_X_MIN) / float(self.VIEW_X_MAX - self.VIEW_X_MIN)
        if name == 'view_y':
            return (self.view_dist_y - self.VIEW_Y_MIN) / float(self.VIEW_Y_MAX - self.VIEW_Y_MIN)
        return 0.0

    def set_slider_ratio(self, name, ratio):
        ratio = max(0.0, min(1.0, ratio))
        if name == 'music':
            self.music_volume = ratio
            try:
                pygame.mixer.music.set_volume(self.music_volume)
            except Exception:
                pass
        elif name == 'sound':
            self.sound_volume = ratio
        elif name == 'view_x':
            self.view_dist_x = int(round(self.VIEW_X_MIN + ratio * (self.VIEW_X_MAX - self.VIEW_X_MIN)))
            self._light_cache_key = None
        elif name == 'view_y':
            self.view_dist_y = int(round(self.VIEW_Y_MIN + ratio * (self.VIEW_Y_MAX - self.VIEW_Y_MIN)))
            self._light_cache_key = None

    def handle_settings_press(self, mx, my):
        """Нажатие в меню настроек. Возвращает True, если оно что-то задело."""
        L = self.get_settings_layout()
        if L['back_btn'].collidepoint((mx, my)):
            self.settings_open = False
            self.dragging_slider = None
            self.save_settings()
            return True
        for i, r in enumerate(L['gfx_btns']):
            if r.collidepoint((mx, my)):
                self.set_graphics_quality(i)
                self.save_settings()
                return True
        for name, y in L['sliders_y'].items():
            track = pygame.Rect(L['slider_x'] - 12, y - 18, L['slider_width'] + 24, 42)
            if track.collidepoint((mx, my)):
                self.dragging_slider = name
                self.set_slider_ratio(name, (mx - L['slider_x']) / float(L['slider_width']))
                return True
        return False

    def handle_settings_drag(self, mx):
        if self.dragging_slider:
            L = self.get_settings_layout()
            self.set_slider_ratio(self.dragging_slider, (mx - L['slider_x']) / float(L['slider_width']))

    def draw_settings_menu(self):
        try:
            overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            overlay.fill((0, 0, 0, 210))
            self.screen.blit(overlay, (0, 0))
            
            L = self.get_settings_layout()
            ui_rect = L['ui_rect']
            self.draw_ui_panel(ui_rect, "НАСТРОЙКИ")
            slider_x, slider_width = L['slider_x'], L['slider_width']
            mouse_pos = pygame.mouse.get_pos()
            
            gfx_label = self.small_font.render("ГРАФИКА", True, self.UI_TEXT_DIM)
            self.screen.blit(gfx_label, (slider_x, L['gfx_label_y']))
            for i, r in enumerate(L['gfx_btns']):
                name = self.GRAPHICS_PRESETS[i][0]
                self.draw_type_choice_button(r, name, i == self.graphics_quality)
            
            def draw_slider(label, value, slider_y):
                label_text = self.small_font.render(label, True, self.UI_TEXT)
                self.screen.blit(label_text, (slider_x, slider_y - 26))
                track_rect = pygame.Rect(slider_x, slider_y, slider_width, 6)
                pygame.draw.rect(self.screen, (18, 19, 24), track_rect, border_radius=3)
                fill_width = int(slider_width * value)
                if fill_width > 0:
                    pygame.draw.rect(self.screen, self.UI_ACCENT, (slider_x, slider_y, fill_width, 6), border_radius=3)
                handle_x = slider_x + fill_width
                handle_y = slider_y + 3
                hover = math.hypot(mouse_pos[0] - handle_x, mouse_pos[1] - handle_y) < 14
                handle_color = (255, 210, 130) if hover else self.UI_ACCENT
                pygame.draw.circle(self.screen, handle_color, (handle_x, handle_y), 11)
                pygame.draw.circle(self.screen, (255, 255, 255), (handle_x, handle_y), 11, 2)
            
            ys = L['sliders_y']
            draw_slider(f"Громкость музыки: {int(self.music_volume * 100)}%", self.music_volume, ys['music'])
            draw_slider(f"Громкость звуков: {int(self.sound_volume * 100)}%", self.sound_volume, ys['sound'])
            draw_slider(f"Дальность прорисовки по X: {self.view_dist_x} бл.", self.get_slider_ratio('view_x'), ys['view_x'])
            draw_slider(f"Дальность прорисовки по Y: {self.view_dist_y} бл.", self.get_slider_ratio('view_y'), ys['view_y'])
            
            self.draw_ui_button(L['back_btn'], "Назад")
        except Exception:
            pass

    def draw_mods_menu(self):
        try:
            overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            overlay.fill((0, 0, 0, 210))
            self.screen.blit(overlay, (0, 0))
            
            layout = self.get_mods_menu_layout()
            ui_rect = layout['ui_rect']
            ui_x, ui_y = layout['ui_x'], layout['ui_y']
            mods_area = layout['mods_area']
            
            self.draw_ui_panel(ui_rect, "МОДЫ")
            
            mods_title = self.small_font.render("ДОСТУПНЫЕ МОДЫ", True, self.UI_TEXT_DIM)
            self.screen.blit(mods_title, (mods_area.x, mods_area.y - 26))
            
            pygame.draw.rect(self.screen, self.UI_BG_LIGHT, mods_area, border_radius=10)
            pygame.draw.rect(self.screen, self.UI_BORDER, mods_area, 2, border_radius=10)
            
            if len(self.mod_manager.available_mods) == 0:
                no_mods = self.font.render("Нет установленных модов", True, self.UI_TEXT_DIM)
                self.screen.blit(no_mods, (mods_area.centerx - no_mods.get_width()//2, mods_area.centery))
            else:
                mods_per_page = 5
                start_index = max(0, self.mods_select_index - 2)
                end_index = min(len(self.mod_manager.available_mods), start_index + mods_per_page)
                row_h = mods_area.height // mods_per_page
                
                for i in range(start_index, end_index):
                    mod = self.mod_manager.available_mods[i]
                    mod_y = mods_area.y + 20 + (i - start_index) * row_h
                    
                    mod_rect = pygame.Rect(mods_area.x + 10, mod_y, mods_area.width - 20, row_h - 10)
                    
                    selected = i == self.mods_select_index
                    bg_color = (58, 62, 80) if selected else self.UI_SLOT
                    border_color = self.UI_ACCENT if selected else self.UI_SLOT_BORDER
                    pygame.draw.rect(self.screen, bg_color, mod_rect, border_radius=8)
                    pygame.draw.rect(self.screen, border_color, mod_rect, 2, border_radius=8)
                    
                    name_color = self.UI_TEXT if mod['enabled'] else self.UI_TEXT_DIM
                    name_text = self.font.render(mod['name'], True, name_color)
                    self.screen.blit(name_text, (mod_rect.x + 20, mod_rect.y + 10))
                    
                    info_text = self.small_font.render(f"Версия: {mod['version']} · Автор: {mod['author']}", True, self.UI_TEXT_DIM)
                    self.screen.blit(info_text, (mod_rect.x + 20, mod_rect.y + 38))
                    
                    status_text = "ВКЛЮЧЕН" if mod['enabled'] else "ВЫКЛЮЧЕН"
                    status_color = self.UI_GOOD if mod['enabled'] else self.UI_BAD
                    status_surface = self.small_font.render(status_text, True, status_color)
                    self.screen.blit(status_surface, (mod_rect.right - 110, mod_rect.y + 25))
            
            if len(self.mod_manager.available_mods) > 0:
                selected_mod = self.mod_manager.available_mods[self.mods_select_index]
                btn_text = "Выключить" if selected_mod['enabled'] else "Включить"
                btn_enabled = True
            else:
                btn_text = "Нет модов"
                btn_enabled = False
            self.draw_ui_button(layout['toggle_btn'], btn_text, btn_enabled, self.small_font)
            self.draw_ui_button(layout['refresh_btn'], "Обновить", True, self.small_font)
            self.draw_ui_button(layout['tutorial_btn'], "Туториал", True, self.small_font)
            self.draw_ui_button(layout['close_btn'], "Закрыть", True, self.small_font)
            
            hints_y = ui_rect.bottom - 46
            hint1 = self.small_font.render("Стрелки Вверх/Вниз — выбор мода  ·  Enter — включить/выключить", True, self.UI_TEXT_DIM)
            hint2 = self.small_font.render("Туториал — как создавать моды для игры", True, self.UI_TEXT_DIM)
            
            self.screen.blit(hint1, (ui_rect.centerx - hint1.get_width()//2, hints_y))
            self.screen.blit(hint2, (ui_rect.centerx - hint2.get_width()//2, hints_y + 20))
        except:
            pass

    def draw_mods_tutorial(self, scroll_offset=0):
        try:
            overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            overlay.fill((0, 0, 0, 220))
            self.screen.blit(overlay, (0, 0))
            
            ui_width = min(1000, int(WIDTH * 0.95))
            ui_height = min(800, int(HEIGHT * 0.9))
            ui_x, ui_y = (WIDTH - ui_width) // 2, (HEIGHT - ui_height) // 2
            ui_rect = pygame.Rect(ui_x, ui_y, ui_width, ui_height)
            
            self.draw_ui_panel(ui_rect, "ТУТОРИАЛ ПО СОЗДАНИЮ МОДОВ", self.small_font)
            
            content_x = ui_x + 50
            header_h = 90  # место под заголовок, не прокручивается
            footer_h = 70  # место под кнопку закрытия, не прокручивается
            viewport_rect = pygame.Rect(ui_x, ui_y + header_h, ui_width, ui_height - header_h - footer_h)
            
            tutorial_content = [
                ("Как создать мод для Teraflat:", [
                    "1. Создайте папку в директории 'mods' (например, 'my_texture_pack')",
                    "2. Создайте файл mod.xml с метаданными мода",
                    "3. Создайте папку 'textures' и поместите туда PNG-текстуры",
                    "4. Имена файлов должны соответствовать оригинальным текстурам",
                    "5. Мод можно упаковать в ZIP-архив с расширением .modpack"
                ]),
                ("Формат файла mod.xml:", [
                    '<?xml version="1.0" encoding="UTF-8"?>',
                    '<mod id="my_mod" name="Мой текстурный пак" version="1.0" author="Ваше Имя">',
                    '  <description>Описание вашего мода</description>',
                    '  <dependencies>',
                    '    <!-- Опционально: зависимости от других модов -->',
                    '  </dependencies>',
                    '</mod>'
                ]),
                ("Поддерживаемые текстуры:", [
                    "grass.png, dirt.png, stone.png, water.png, lava.png",
                    "wood.png, leaves.png, sand.png, plank.png, snow.png",
                    "ash.png, cactus.png, pine_leaves.png, pine_log.png",
                    "pine_plank.png, stick.png, crafting_table.png, glass.png",
                    "wooden_door_closed.png, wooden_door_open.png, iron_door_closed.png, iron_door_open.png",
                    "pine_door_closed.png, pine_door_open.png",
                    "furnace.png, coal_ore.png, iron_ore.png, gold_ore.png",
                    "diamond_ore.png, coal.png, iron_ingot.png, gold_ingot.png",
                    "diamond.png, torch.png, pine_wood.png",
                    "Все инструменты и оружие (wooden_pickaxe.png и т.д.)",
                    "Все блоки (stone_brick.png, iron_block.png и т.д.)"
                ]),
                ("Пример структуры мода:", [
                    "my_texture_pack/",
                    "  ├── mod.xml",
                    "  └── textures/",
                    "      ├── grass.png",
                    "      ├── dirt.png",
                    "      └── stone.png"
                ]),
                ("Советы:", [
                    "• Текстуры должны быть в формате PNG",
                    "• Размер текстур должен быть кратным 16x16 или 32x32",
                    "• Игра автоматически масштабирует текстуры до нужного размера",
                    "• Для прозрачности используйте альфа-канал в PNG",
                    "• Моды загружаются при запуске игры",
                    "• Включенные моды применяются к текстурам автоматически"
                ]),
                ("Отладка:", [
                    "• Проверяйте консоль на наличие ошибок загрузки модов",
                    "• Убедитесь что файлы имеют правильные имена",
                    "• Убедитесь что XML-файл правильно отформатирован",
                    "• Перезагрузите моды через меню 'Обновить'",
                    "• Проверьте что мод включен в меню модов"
                ])
            ]
            
            # Считаем полную высоту контента заранее, чтобы знать пределы
            # прокрутки и подготовить внутреннюю поверхность нужного размера.
            line_h = 25
            section_title_h = 40
            section_gap = 20
            total_h = 0
            for _, section_content in tutorial_content:
                total_h += section_title_h + len(section_content) * line_h + section_gap
            
            content_width = ui_width - 60
            content_surface = pygame.Surface((content_width, max(total_h, viewport_rect.height)), pygame.SRCALPHA)
            
            current_y = 0
            for section_title, section_content in tutorial_content:
                title_surface = self.font.render(section_title, True, self.UI_ACCENT)
                content_surface.blit(title_surface, (0, current_y))
                current_y += section_title_h
                
                for line in section_content:
                    line_surface = self.small_font.render(line, True, self.UI_TEXT_DIM)
                    content_surface.blit(line_surface, (20, current_y))
                    current_y += line_h
                
                current_y += section_gap
            
            max_scroll = max(0, total_h - viewport_rect.height)
            scroll_offset = max(0, min(scroll_offset, max_scroll))
            
            self.screen.set_clip(viewport_rect)
            self.screen.blit(content_surface, (content_x, viewport_rect.y - scroll_offset))
            self.screen.set_clip(None)
            
            # Индикатор прокрутки, если контент не помещается целиком
            if max_scroll > 0:
                track_rect = pygame.Rect(ui_rect.right - 20, viewport_rect.y, 8, viewport_rect.height)
                pygame.draw.rect(self.screen, self.UI_BG_LIGHT, track_rect, border_radius=4)
                thumb_h = max(24, int(viewport_rect.height * (viewport_rect.height / total_h)))
                thumb_y = track_rect.y + int((track_rect.height - thumb_h) * (scroll_offset / max_scroll))
                pygame.draw.rect(self.screen, self.UI_ACCENT, (track_rect.x, thumb_y, 8, thumb_h), border_radius=4)
            
            close_btn = pygame.Rect(ui_rect.centerx - 80, ui_rect.bottom - 60, 160, 50)
            self.draw_ui_button(close_btn, "Закрыть", True, self.font)
            
            self.mods_tutorial_close_btn = close_btn
            self.mods_tutorial_max_scroll = max_scroll
        except:
            pass

    def update_player(self):
        keys = pygame.key.get_pressed()
        old_health = self.health
        
        try:
            if self.game_mode == "CREATIVE":
                # Игрок в креативе бессмертен: не даём здоровью упасть ниже
                # максимума и никогда не показываем экран смерти, даже если
                # какой-то источник урона забудет проверить game_mode.
                self.health = self.max_health
            
            if self.health <= 0 and not self.show_death_screen and self.game_mode != "CREATIVE":
                self.show_death_screen = True
                self.death_timer = time.time()
                self.play_death_sound()
            
            if self.show_death_screen:
                if time.time() - self.death_timer > 3:
                    self.show_death_screen = False
                    self.health = self.max_health
                    self.player_rect.topleft = (WIDTH//2, 100)
                    self.vel_y = 0
                    self.camera_x = 0
                    self.camera_y = 0
                    self.fall_distance = 0
                return
            
            px, py = int(self.player_rect.centerx // 40), int(self.player_rect.centery // 40)
            feet_x, feet_y = int(self.player_rect.centerx // 40), int((self.player_rect.bottom - 2) // 40)
            curr_block = self.world.get((px, py), [0])[0]
            feet_block = self.world.get((feet_x, feet_y), [0])[0]
            # Считаем игрока "в воде", если вода на уровне его центра ИЛИ у
            # его ног - иначе при выныривании in_water отключался слишком
            # рано (по центру тела уже воздух, а ноги ещё в воде), гравитация
            # включалась резко и не давала долезть на блок впереди.
            in_water = curr_block == WATER or feet_block == WATER
            in_lava = curr_block == LAVA
            
            if in_lava and self.timer % 25 == 0 and self.game_mode == "SURVIVAL": 
                self.health -= 2
            
            self.is_swimming = in_water
            
            if self.on_ground and self.fall_distance > 3 and self.game_mode == "SURVIVAL":
                fall_damage = int((self.fall_distance - 3) * 2)
                if fall_damage > 0:
                    self.health -= fall_damage
                    self.play_damage_sound()
                self.fall_distance = 0
            elif self.on_ground:
                self.fall_distance = 0
            
            if self.game_mode == "SURVIVAL":
                if in_water:
                    head_y = int((self.player_rect.top - 2) // 40)
                    head_block = self.world.get((px, head_y), [EMPTY])[0]
                    head_is_air = head_block != WATER and (head_block == EMPTY or head_block in self.non_solid_blocks)
                    if keys[pygame.K_SPACE] or self.virtual_jump_pressed:
                        if head_is_air and curr_block != WATER:
                            # Голова уже над водой и путь свободен - даём
                            # полноценный импульс вынырнуть/забраться на
                            # уступ, а не слабое плавательное подрагивание.
                            self.vel_y = max(self.vel_y - 1.2, -8)
                        else:
                            self.vel_y = max(self.vel_y - 0.4, -4)
                    else:
                        self.vel_y = min(self.vel_y + 0.1, 2)
                        
                    self.vel_y = max(-8, min(2, self.vel_y))
                else:
                    self.vel_y += 0.8
                    self.vel_y = min(self.vel_y, 20)
                
                if not self.on_ground and self.vel_y > 0:
                    self.fall_distance = max(self.fall_distance, (self.last_ground_y - self.player_rect.bottom) / TILE_SIZE)
                else:
                    self.last_ground_y = self.player_rect.bottom
                
                self.player_rect.y += self.vel_y
                self.collide(0, self.vel_y)
            elif self.creative_flying:
                # Свободный полёт - включается/выключается отдельно (клавиша F),
                # по умолчанию выключен даже в креативе.
                if keys[pygame.K_w] or keys[pygame.K_SPACE] or self.virtual_jump_pressed: 
                    self.player_rect.y -= 6
                if keys[pygame.K_s] or keys[pygame.K_LSHIFT]: 
                    self.player_rect.y += 6
                self.vel_y = 0
                self.fall_distance = 0
            else:
                # Креатив без полёта - обычная гравитация, но без урона
                # от падения (тот блок уже отфильтрован выше по game_mode).
                # В воде даём то же управление всплытием, что и в выживании -
                # иначе игрок в креативе просто тонет без возможности
                # выплыть, раз обычная гравитация не учитывает воду.
                if in_water:
                    head_y = int((self.player_rect.top - 2) // 40)
                    head_block = self.world.get((px, head_y), [EMPTY])[0]
                    head_is_air = head_block != WATER and (head_block == EMPTY or head_block in self.non_solid_blocks)
                    if keys[pygame.K_SPACE] or self.virtual_jump_pressed:
                        if head_is_air and curr_block != WATER:
                            self.vel_y = max(self.vel_y - 1.2, -8)
                        else:
                            self.vel_y = max(self.vel_y - 0.4, -4)
                    else:
                        self.vel_y = min(self.vel_y + 0.1, 2)
                    self.vel_y = max(-8, min(2, self.vel_y))
                else:
                    self.vel_y += 0.8
                    self.vel_y = min(self.vel_y, 20)
                
                if not self.on_ground and self.vel_y > 0:
                    self.fall_distance = max(self.fall_distance, (self.last_ground_y - self.player_rect.bottom) / TILE_SIZE)
                else:
                    self.last_ground_y = self.player_rect.bottom
                
                self.player_rect.y += self.vel_y
                self.collide(0, self.vel_y)
                
            keyboard_dx = keys[pygame.K_d] - keys[pygame.K_a]
            dx = (keyboard_dx + self.virtual_move_x)
            dx = max(-1, min(1, dx)) * (5 if not in_water else 2.5)
            
            if dx > 0:
                self.player_facing = "right"
            elif dx < 0:
                self.player_facing = "left"
            
            x_before = self.player_rect.x
            self.player_rect.x += dx
            self.collide(dx, 0)
            
            # Автопрыжок на тач-устройствах: упёрлись в ступеньку высотой в
            # блок - перепрыгиваем сами, не заставляя жать кнопку прыжка.
            if (self.touch_device_detected and self.on_ground and not in_water
                    and abs(self.virtual_move_x) > 0.3 and dx != 0
                    and not (self.game_mode == "CREATIVE" and self.creative_flying)):
                if abs(self.player_rect.x - x_before) < abs(dx) * 0.5:
                    step = 1 if dx > 0 else -1
                    probe = self.player_rect.move(step * 4, -TILE_SIZE - 2)
                    if not self._rect_hits_solid(probe):
                        self.vel_y = -9.5
                        self.fall_distance = 0
            
            if (keys[pygame.K_SPACE] or self.virtual_jump_pressed) and self.on_ground and not in_water and not (self.game_mode == "CREATIVE" and self.creative_flying): 
                self.vel_y = -14
                self.fall_distance = 0
            
            if self.world_type == "LIMITED":
                max_x = 300 * TILE_SIZE
                if self.player_rect.left < 0:
                    self.player_rect.left = 0
                elif self.player_rect.right > max_x:
                    self.player_rect.right = max_x
            
            if self.health < old_health and not in_lava: 
                self.play_damage_sound()
            
            self.camera_x += (self.player_rect.x - self.camera_x - WIDTH//2) * 0.1
            self.camera_y += (self.player_rect.y - self.camera_y - HEIGHT//2) * 0.1
        except:
            pass

    def _rect_hits_solid(self, rect):
        """Есть ли в прямоугольнике твёрдый блок (для автопрыжка)."""
        T = TILE_SIZE
        for x in range(rect.left // T, (rect.right - 1) // T + 1):
            for y in range(rect.top // T, (rect.bottom - 1) // T + 1):
                o = self.get_multitile_origin(x, y)
                if o is not None:
                    if rect.colliderect(self.get_multitile_rect(o[0], o[1], self.world[o][0])):
                        return True
                    continue
                b = self.world.get((x, y))
                if b is None or b[0] in self.non_solid_blocks:
                    continue
                if b[0] in (WOODEN_DOOR, PINE_DOOR):
                    st = self.door_states.get((x, y))
                    if st and st[1]:
                        continue
                    if rect.colliderect(pygame.Rect(x * T, y * T - T, T, T * 2)):
                        return True
                    continue
                return True
        return False

    def collide(self, dx, dy):
        if dy != 0: 
            self.on_ground = False
            
        try:
            px, py = int(self.player_rect.x // 40), int(self.player_rect.y // 40)
            
            for x in range(px - 1, px + 3):
                for y in range(py - 1, py + 4):
                    if (x, y) not in self.world:
                        continue
                        
                    block_data = self.world.get((x, y), [EMPTY])
                    block_id = block_data[0]
                    
                    if block_id in self.non_solid_blocks:
                        continue
                    
                    if block_id in [WOODEN_DOOR, PINE_DOOR]:
                        door_key = (x, y)
                        if door_key in self.door_states:
                            door_data = self.door_states[door_key]
                            is_open = door_data[1]
                            
                            if is_open:
                                continue
                            
                            br = pygame.Rect(x*40, y*40 - TILE_SIZE, TILE_SIZE, TILE_SIZE * 2)
                            
                            if self.player_rect.colliderect(br):
                                if dy > 0:
                                    self.player_rect.bottom = br.top
                                    self.vel_y = 0
                                    self.on_ground = True
                                    self.fall_distance = 0
                                elif dy < 0:
                                    self.player_rect.top = br.bottom
                                    self.vel_y = 0
                                elif dx > 0:
                                    self.player_rect.right = br.left
                                elif dx < 0:
                                    self.player_rect.left = br.right
                        
                        continue
                    
                    if block_id in (CRAFTING_TABLE, FURNACE):
                        br = self.get_multitile_rect(x, y, block_id)
                    else:
                        br = pygame.Rect(x*40, y*40, 40, 40)
                    if self.player_rect.colliderect(br):
                        if dy > 0:
                            self.player_rect.bottom = br.top
                            self.vel_y = 0
                            self.on_ground = True
                            self.fall_distance = 0
                        elif dy < 0:
                            self.player_rect.top = br.bottom
                            self.vel_y = 0
                        elif dx > 0:
                            self.player_rect.right = br.left
                        elif dx < 0:
                            self.player_rect.left = br.right
        except:
            pass

    def draw_mining_progress(self):
        if self.is_mining and self.mining_target is not None:
            try:
                block_x, block_y = self.mining_target
                if (block_x, block_y) in self.world:
                    block_id = self.world[(block_x, block_y)][0]
                    mining_time = self.mining_times.get(block_id, 1.0)
                    
                    tool_id = self.get_selected_item()
                    multiplier = self.get_mining_multiplier(block_id, tool_id)
                    mining_time /= multiplier
                    
                    pygame.draw.rect(self.screen, (50, 50, 50), self.mining_bar_rect)
                    pygame.draw.rect(self.screen, (100, 100, 100), self.mining_bar_rect, 2)
                    
                    fill_width = int(self.mining_bar_rect.width * self.mining_progress)
                    fill_rect = pygame.Rect(
                        self.mining_bar_rect.x,
                        self.mining_bar_rect.y,
                        fill_width,
                        self.mining_bar_rect.height
                    )
                    
                    if block_id == STONE:
                        color = (150, 150, 150)
                    elif block_id == WOOD or block_id == PINE_LOG or block_id == PINE_WOOD:
                        color = (139, 69, 19)
                    elif block_id == PINE_PLANK:
                        color = (80, 60, 40)
                    elif block_id == LEAVES or block_id == PINE_LEAVES:
                        color = (34, 139, 34)
                    elif block_id == GLASS:
                        color = (100, 200, 255)
                    elif block_id in [WOODEN_DOOR, PINE_DOOR]:
                        color = (139, 90, 43)
                    elif block_id in [COAL_ORE, COAL]:
                        color = (30, 30, 30)
                    elif block_id in [IRON_ORE, IRON_INGOT, IRON_BLOCK]:
                        color = (180, 180, 180)
                    elif block_id in [GOLD_ORE, GOLD_INGOT, GOLD_BLOCK]:
                        color = (255, 215, 0)
                    elif block_id in [DIAMOND_ORE, DIAMOND, DIAMOND_BLOCK]:
                        color = (100, 200, 255)
                    elif block_id == FURNACE:
                        color = (100, 100, 100)
                    elif block_id == TORCH:
                        color = (255, 200, 0)
                    else:
                        color = (100, 200, 100)
                    
                    pygame.draw.rect(self.screen, color, fill_rect)
                    
                    tool_text = ""
                    if tool_id in [WOODEN_PICKAXE, STONE_PICKAXE, IRON_PICKAXE, GOLD_PICKAXE, DIAMOND_PICKAXE]:
                        tool_text = " (Киркой)"
                    elif tool_id in [WOODEN_AXE, STONE_AXE, IRON_AXE, GOLD_AXE, DIAMOND_AXE]:
                        tool_text = " (Топором)"
                    
                    block_names = {
                        GRASS: "Трава", DIRT: "Земля", STONE: "Камень", 
                        WOOD: "Дерево", PINE_LOG: "Ель", LEAVES: "Листья",
                        PINE_LEAVES: "Хвоя", SAND: "Песок", PLANK: "Доски",
                        PINE_PLANK: "Еловые доски",
                        SNOW_GRASS: "Снег", ASH: "Пепел", CACTUS: "Кактус",
                        CRAFTING_TABLE: "Верстак", GLASS: "Стекло",
                        WOODEN_DOOR: "Дерев. дверь",
                        PINE_DOOR: "Еловая дверь",
                        FURNACE: "Печка", COAL_ORE: "Угольная руда",
                        IRON_ORE: "Железная руда", GOLD_ORE: "Золотая руда",
                        DIAMOND_ORE: "Алмазная руда", COAL: "Уголь",
                        IRON_INGOT: "Железный слиток", GOLD_INGOT: "Золотой слиток",
                        DIAMOND: "Алмаз", STONE_BRICK: "Каменный кирпич",
                        IRON_BLOCK: "Железный блок", GOLD_BLOCK: "Золотой блок",
                        DIAMOND_BLOCK: "Алмазный блок", TORCH: "Факел",
                        PINE_WOOD: "Еловая древесина"
                    }
                    
                    block_name = block_names.get(block_id, "Блок")
                    time_left = max(0, mining_time * (1 - self.mining_progress))
                    
                    text = f"{block_name}{tool_text}: {time_left:.1f}с"
                    text_surface = self.font.render(text, True, (255, 255, 255))
                    text_rect = text_surface.get_rect(center=self.mining_bar_rect.center)
                    self.screen.blit(text_surface, text_rect)
            except:
                pass

    def draw_hotbar(self):
        try:
            inv_x = WIDTH // 2 - 240
            hotbar_y = HEIGHT - 100
            
            pygame.draw.rect(self.screen, (50, 50, 50, 200), 
                            (inv_x - 10, hotbar_y - 10, 
                             self.hotbar_slots * 48 + 20, 62))
            
            for i in range(self.hotbar_slots):
                slot_x = inv_x + i * 48
                slot_y = hotbar_y
                
                if i == self.selected_slot:
                    pygame.draw.rect(self.screen, (255, 255, 255), 
                                   (slot_x - 2, slot_y - 2, 46, 46), 3)
                    pygame.draw.rect(self.screen, (100, 100, 100, 150), 
                                   (slot_x, slot_y, 42, 42))
                else:
                    pygame.draw.rect(self.screen, (80, 80, 80), 
                                   (slot_x, slot_y, 42, 42), 2)
                
                if self.hotbar[i] is not None and self.hotbar[i] in self.textures:
                    if self.hotbar[i] in [WOODEN_DOOR, PINE_DOOR]:
                        icon = pygame.transform.scale(self.textures[self.hotbar[i]], (34, 34))
                    else:
                        icon = pygame.transform.scale(self.textures[self.hotbar[i]], (34, 34))
                    self.screen.blit(icon, (slot_x + 4, slot_y + 4))
                    
                    if self.hotbar_counts[i] > 1:
                        count_text = self.small_font.render(str(self.hotbar_counts[i]), 
                                                           True, (255, 255, 255))
                        self.screen.blit(count_text, (slot_x + 25, slot_y + 25))
                
                num_text = self.small_font.render(str(i + 1), True, (200, 200, 200))
                self.screen.blit(num_text, (slot_x + 2, slot_y + 2))
        except:
            pass

    # === Единая система стиля UI ===
    # Общая палитра и хелперы, чтобы инвентарь, верстак, печка, пауза,
    # настройки и меню модов выглядели как один интерфейс, а не набор
    # разностильных панелей.
    UI_BG = (24, 26, 32)          # фон панели
    UI_BG_LIGHT = (34, 37, 45)    # чуть светлее (заголовки, подложки)
    UI_BORDER = (90, 100, 120)    # окантовка панели
    UI_ACCENT = (240, 180, 80)    # янтарный акцент (заголовки, прогресс, выделение)
    UI_SLOT = (44, 47, 56)        # фон слота инвентаря
    UI_SLOT_BORDER = (78, 84, 98)
    UI_SLOT_HOVER = (58, 62, 74)
    UI_TEXT = (235, 235, 240)
    UI_TEXT_DIM = (165, 168, 178)
    UI_GOOD = (90, 190, 100)      # можно скрафтить / успех
    UI_BAD = (205, 90, 90)        # нельзя / ошибка / закрыть
    UI_RADIUS = 14

    def draw_ui_panel(self, rect, title=None, title_font=None):
        """Рисует стандартную панель: тень, тёмный фон, окантовка, плашка
        заголовка. Возвращает ничего - просто кладёт панель на self.screen."""
        shadow_rect = rect.copy()
        shadow_rect.move_ip(6, 8)
        pygame.draw.rect(self.screen, (0, 0, 0, 90), shadow_rect, border_radius=self.UI_RADIUS)
        pygame.draw.rect(self.screen, self.UI_BG, rect, border_radius=self.UI_RADIUS)
        pygame.draw.rect(self.screen, self.UI_BORDER, rect, 2, border_radius=self.UI_RADIUS)
        
        if title:
            header_rect = pygame.Rect(rect.x, rect.y, rect.width, 58)
            pygame.draw.rect(self.screen, self.UI_BG_LIGHT, header_rect,
                              border_top_left_radius=self.UI_RADIUS, border_top_right_radius=self.UI_RADIUS)
            pygame.draw.line(self.screen, self.UI_BORDER, (rect.x + 2, rect.y + 58), (rect.right - 2, rect.y + 58), 2)
            font = title_font or self.font
            title_surf = font.render(title, True, self.UI_ACCENT)
            self.screen.blit(title_surf, (rect.centerx - title_surf.get_width()//2, rect.y + 16))

    def draw_ui_close_button(self, rect):
        """Единая крестик-кнопка закрытия для любой панели."""
        mouse_pos = pygame.mouse.get_pos()
        hover = rect.collidepoint(mouse_pos)
        color = (225, 100, 100) if hover else self.UI_BAD
        pygame.draw.rect(self.screen, color, rect, border_radius=8)
        close_text = self.font.render("×", True, (255, 255, 255))
        self.screen.blit(close_text, (rect.centerx - close_text.get_width()//2, rect.centery - close_text.get_height()//2 - 2))

    def draw_ui_slot(self, rect, item_id=None, count=1, hover=False):
        """Единый слот инвентаря/крафта: фон, окантовка, иконка, счётчик."""
        bg = self.UI_SLOT_HOVER if hover else self.UI_SLOT
        pygame.draw.rect(self.screen, bg, rect, border_radius=8)
        pygame.draw.rect(self.screen, self.UI_SLOT_BORDER, rect, 2, border_radius=8)
        
        if item_id is not None and item_id in self.textures:
            pad = 6
            icon = pygame.transform.scale(self.textures[item_id], (rect.width - pad*2, rect.height - pad*2))
            self.screen.blit(icon, (rect.x + pad, rect.y + pad))
            
            if count > 1:
                count_text = self.small_font.render(str(count), True, self.UI_TEXT)
                shadow = self.small_font.render(str(count), True, (0, 0, 0))
                tx = rect.right - count_text.get_width() - 4
                ty = rect.bottom - count_text.get_height() - 2
                self.screen.blit(shadow, (tx + 1, ty + 1))
                self.screen.blit(count_text, (tx, ty))

    def get_mods_menu_layout(self):
        """Единый источник геометрии меню модов: и отрисовка, и все клик-
        обработчики берут прямоугольники отсюда, чтобы никогда не разойтись
        (раньше формула была продублирована в 4 местах). Внутренние отступы
        считаются в долях от ui_width/ui_height, а не в жёстких пикселях,
        поэтому раскладка не ломается при сжатии панели на маленьких
        экранах.
        """
        ui_width = min(900, int(WIDTH * 0.95))
        ui_height = min(700, int(HEIGHT * 0.9))
        ui_x, ui_y = (WIDTH - ui_width) // 2, (HEIGHT - ui_height) // 2
        ui_rect = pygame.Rect(ui_x, ui_y, ui_width, ui_height)
        
        pad_x = int(ui_width * 0.056)   # ~50/900
        area_y_off = int(ui_height * 0.143)  # ~100/700
        area_w = ui_width - pad_x * 2
        area_h = int(ui_height * 0.571)  # ~400/700
        
        mods_area = pygame.Rect(ui_x + pad_x, ui_y + area_y_off, area_w, area_h)
        btn_y = mods_area.bottom + int(ui_height * 0.043)  # ~30/700
        btn_w = int(ui_width * 0.2)   # ~180/900
        btn_h = int(ui_height * 0.071)  # ~50/700
        btn_gap = int(ui_width * 0.222)  # ~200/900 (расстояние между стартами кнопок)
        
        toggle_btn = pygame.Rect(ui_x + pad_x, btn_y, btn_w, btn_h)
        refresh_btn = pygame.Rect(ui_x + pad_x + btn_gap, btn_y, btn_w, btn_h)
        tutorial_btn = pygame.Rect(ui_x + pad_x + btn_gap * 2, btn_y, btn_w, btn_h)
        close_btn = pygame.Rect(ui_x + pad_x + btn_gap * 3, btn_y, btn_w, btn_h)
        
        return {
            'ui_rect': ui_rect, 'ui_x': ui_x, 'ui_y': ui_y,
            'ui_width': ui_width, 'ui_height': ui_height,
            'mods_area': mods_area, 'btn_y': btn_y,
            'toggle_btn': toggle_btn, 'refresh_btn': refresh_btn,
            'tutorial_btn': tutorial_btn, 'close_btn': close_btn,
        }

    def draw_ui_button(self, rect, label, enabled=True, font=None):
        """Единая прямоугольная кнопка с hover-подсветкой (пауза, настройки, крафт)."""
        mouse_pos = pygame.mouse.get_pos()
        hover = enabled and rect.collidepoint(mouse_pos)
        if enabled:
            color = (72, 78, 92) if hover else (56, 60, 72)
            border = self.UI_ACCENT if hover else self.UI_BORDER
            text_color = self.UI_TEXT
        else:
            color = (44, 46, 52)
            border = (60, 62, 68)
            text_color = self.UI_TEXT_DIM
        pygame.draw.rect(self.screen, color, rect, border_radius=10)
        pygame.draw.rect(self.screen, border, rect, 2, border_radius=10)
        f = font or self.font
        text_surf = f.render(label, True, text_color)
        self.screen.blit(text_surf, (rect.centerx - text_surf.get_width()//2, rect.centery - text_surf.get_height()//2))
        return hover

    # === Мобильное управление ===
    # Виртуальный джойстик (движение) слева внизу, кнопки действий справа
    # внизу. Показываются только если обнаружено настоящее touch-устройство
    # (self.touch_device_detected) - на ПК эти элементы не рисуются и не
    # мешают обычному управлению клавиатурой/мышью.
    def get_mobile_scale(self):
        """Масштаб тач-интерфейса под размер экрана (телефон/планшет)."""
        return max(0.8, min(1.7, min(WIDTH, HEIGHT) / 720.0))

    def get_joystick_radius(self):
        return int(72 * self.get_mobile_scale())

    def get_mobile_layout(self):
        """Единое место с геометрией всех тач-кнопок: по ней же рисуем,
        ловим касания и отсекаем синтетические клики мыши (раньше формулы
        дублировались и расходились)."""
        s = self.get_mobile_scale()
        m = int(22 * s)          # отступ от края экрана
        jr = int(60 * s)         # радиус кнопки прыжка
        br = int(42 * s)         # радиус малых кнопок
        gap = int(14 * s)
        sb = int(52 * s)         # сторона квадратных кнопок сверху
        jump = pygame.Rect(WIDTH - m - 2 * jr, HEIGHT - m - 2 * jr, 2 * jr, 2 * jr)
        # Режим ломать/ставить - слева от прыжка (под большой палец),
        # инвентарь - над прыжком.
        mode = pygame.Rect(jump.left - gap - 2 * br, HEIGHT - m - 2 * br, 2 * br, 2 * br)
        inv = pygame.Rect(jump.centerx - br, jump.top - gap - 2 * br, 2 * br, 2 * br)
        pause = pygame.Rect(WIDTH - sb - int(12 * s), int(12 * s), sb, sb)
        debug = pygame.Rect(pause.left - sb - int(10 * s), pause.top, sb, sb)
        # Плавающий джойстик: появляется там, где палец коснулся этой зоны
        zone_top = int(HEIGHT * 0.45)
        joy_zone = pygame.Rect(0, zone_top, int(WIDTH * 0.28), HEIGHT - zone_top)
        R = self.get_joystick_radius()
        idle = (m + R, HEIGHT - m - R)
        return {'jump': jump, 'mode': mode, 'inv': inv, 'pause': pause,
                'debug': debug, 'joy_zone': joy_zone, 'joy_idle': idle}

    def mobile_menu_open(self):
        return bool(self.inventory_open or self.crafting_table_open or
                    self.furnace_open is not None or self.mods_menu_open or
                    self.paused or self.show_death_screen)

    def mobile_ui_hit(self, pos):
        """True, если точка попала в тач-кнопку (клик по миру игнорируем)."""
        L = self.get_mobile_layout()
        if L['pause'].collidepoint(pos) or L['debug'].collidepoint(pos) or L['inv'].collidepoint(pos):
            return True
        if self.mobile_menu_open():
            return False
        return (L['jump'].collidepoint(pos) or L['mode'].collidepoint(pos) or
                L['joy_zone'].collidepoint(pos))

    def get_virtual_joystick_rect(self):
        return self.get_mobile_layout()['joy_zone']

    def get_virtual_jump_rect(self):
        return self.get_mobile_layout()['jump']

    def update_virtual_jump(self):
        self.virtual_jump_pressed = self.virtual_jump_btn_held or self.virtual_stick_up

    def update_virtual_joystick(self, touch_x, touch_y):
        """Двигает стик за пальцем (в пределах базы). Влево/вправо - с
        мёртвой зоной, свайп вверх = прыжок."""
        ox, oy = self.joystick_origin
        dx, dy = touch_x - ox, touch_y - oy
        dist = math.hypot(dx, dy)
        max_dist = self.get_joystick_radius()
        if dist > max_dist:
            dx = dx / dist * max_dist
            dy = dy / dist * max_dist
        self.joystick_pos = (ox + dx, oy + dy)
        nx = dx / max_dist
        dead = 0.18
        if abs(nx) < dead:
            self.virtual_move_x = 0.0
        else:
            self.virtual_move_x = math.copysign((abs(nx) - dead) / (1 - dead), nx)
        self.virtual_stick_up = (dy / max_dist) < -0.65
        self.update_virtual_jump()

    def _mobile_circle_btn(self, rect, label=None, active=False, alpha=170):
        d = rect.width
        surf = pygame.Surface((d, d), pygame.SRCALPHA)
        bg = self.UI_ACCENT if active else self.UI_BG
        pygame.draw.circle(surf, (*bg, 215 if active else alpha), (d // 2, d // 2), d // 2 - 2)
        pygame.draw.circle(surf, (*self.UI_BORDER, 230), (d // 2, d // 2), d // 2 - 2, 3)
        self.screen.blit(surf, rect.topleft)
        if label:
            col = (20, 20, 24) if active else self.UI_TEXT
            t = self.small_font.render(label, True, col)
            self.screen.blit(t, (rect.centerx - t.get_width() // 2, rect.centery - t.get_height() // 2))

    def draw_mobile_controls(self):
        """Рисует тач-управление: плавающий джойстик (слева), прыжок, режим
        ломать/ставить, инвентарь, пауза и отладка."""
        if not self.touch_device_detected or self.state != "PLAYING":
            return
        try:
            L = self.get_mobile_layout()
            s = self.get_mobile_scale()
            # Старые имена атрибутов оставлены для совместимости
            self.virtual_pause_btn_rect = L['pause']
            self.virtual_debug_btn_rect = L['debug']
            self.virtual_inventory_btn_rect = L['inv']
            self.virtual_mode_btn_rect = L['mode']

            # Пауза и отладка - всегда
            for key, label in (('pause', None), ('debug', 'i')):
                r = L[key]
                surf = pygame.Surface((r.width, r.height), pygame.SRCALPHA)
                active = (key == 'debug' and self.show_debug_info)
                bg = self.UI_ACCENT if active else self.UI_BG
                pygame.draw.rect(surf, (*bg, 180), (0, 0, r.width, r.height), border_radius=int(10 * s))
                pygame.draw.rect(surf, (*self.UI_BORDER, 230), (0, 0, r.width, r.height), 2, border_radius=int(10 * s))
                if key == 'pause':
                    bw, bh = int(7 * s), int(r.height * 0.45)
                    top = (r.height - bh) // 2
                    pygame.draw.rect(surf, self.UI_TEXT, (r.width // 2 - bw - int(3 * s), top, bw, bh))
                    pygame.draw.rect(surf, self.UI_TEXT, (r.width // 2 + int(3 * s), top, bw, bh))
                else:
                    t = self.small_font.render(label, True, (20, 20, 24) if active else self.UI_TEXT)
                    surf.blit(t, (r.width // 2 - t.get_width() // 2, r.height // 2 - t.get_height() // 2))
                self.screen.blit(surf, r.topleft)

            if self.paused or self.show_death_screen:
                return

            # Инвентарь - виден и при открытом меню, чтобы его можно было закрыть
            self._mobile_circle_btn(L['inv'], "ИНВ", active=self.inventory_open)

            if self.mobile_menu_open():
                return

            # Джойстик: база там, где палец; в покое - бледная подсказка
            R = self.get_joystick_radius()
            if self.joystick_active:
                center = self.joystick_origin
                base_alpha, stick_pos = 140, self.joystick_pos
            else:
                center = L['joy_idle']
                base_alpha, stick_pos = 70, L['joy_idle']
            base = pygame.Surface((R * 2 + 8, R * 2 + 8), pygame.SRCALPHA)
            c = (base.get_width() // 2, base.get_height() // 2)
            pygame.draw.circle(base, (*self.UI_BG, base_alpha), c, R)
            pygame.draw.circle(base, (*self.UI_BORDER, min(255, base_alpha + 60)), c, R, 3)
            self.screen.blit(base, (center[0] - c[0], center[1] - c[1]))
            sr = int(R * 0.45)
            stick = pygame.Surface((sr * 2 + 4, sr * 2 + 4), pygame.SRCALPHA)
            col = self.UI_ACCENT if self.joystick_active else self.UI_SLOT_BORDER
            pygame.draw.circle(stick, (*col, 230 if self.joystick_active else 120), (sr + 2, sr + 2), sr)
            pygame.draw.circle(stick, (255, 255, 255, 200 if self.joystick_active else 100), (sr + 2, sr + 2), sr, 2)
            self.screen.blit(stick, (int(stick_pos[0]) - sr - 2, int(stick_pos[1]) - sr - 2))

            # Прыжок: большая кнопка со стрелкой вверх
            self._mobile_circle_btn(L['jump'], None, active=self.virtual_jump_pressed)
            jc = L['jump'].center
            a = int(L['jump'].width * 0.22)
            col = (20, 20, 24) if self.virtual_jump_pressed else self.UI_TEXT
            pygame.draw.polygon(self.screen, col, [(jc[0], jc[1] - a), (jc[0] - a, jc[1] + a // 2), (jc[0] + a, jc[1] + a // 2)])
            pygame.draw.rect(self.screen, col, (jc[0] - a // 3, jc[1] + a // 3, 2 * a // 3, a))

            # Режим ломать/ставить
            place = getattr(self, 'mobile_action_mode', 'mine') == 'place'
            self._mobile_circle_btn(L['mode'], "СТАВИТЬ" if place else "ЛОМАТЬ", active=place)
        except Exception:
            pass

    def draw_type_choice_button(self, rect, label, selected):
        """Кнопка-переключатель выбора (например тип мира) - явно показывает,
        какой вариант выбран, в отличие от обычной кнопки действия."""
        mouse_pos = pygame.mouse.get_pos()
        hover = rect.collidepoint(mouse_pos)
        if selected:
            color = (72, 96, 60)
            border = self.UI_GOOD
        else:
            color = (58, 60, 70) if hover else self.UI_SLOT
            border = self.UI_SLOT_BORDER
        pygame.draw.rect(self.screen, color, rect, border_radius=10)
        pygame.draw.rect(self.screen, border, rect, 2, border_radius=10)
        text_color = self.UI_TEXT if selected else self.UI_TEXT_DIM
        text_surf = self.small_font.render(label, True, text_color)
        # Длинную подпись сжимаем, чтобы она не вылезала за кнопку
        max_w = rect.width - 12
        if text_surf.get_width() > max_w and max_w > 10:
            k = max_w / float(text_surf.get_width())
            text_surf = pygame.transform.smoothscale(
                text_surf, (max_w, max(1, int(text_surf.get_height() * k))))
        self.screen.blit(text_surf, (rect.centerx - text_surf.get_width()//2, rect.centery - text_surf.get_height()//2))

    def draw_health(self):
        try:

            heart_x, heart_y = 20, HEIGHT - 50
            hearts_per_row = 10
            
            for i in range(self.max_health // 2):
                heart_pos_x = heart_x + (i % hearts_per_row) * 25
                heart_pos_y = heart_y + (i // hearts_per_row) * 25
                
                if i * 2 + 2 <= self.health:
                    self.screen.blit(self.heart_texture, (heart_pos_x, heart_pos_y))
                elif i * 2 + 1 <= self.health:
                    self.screen.blit(self.half_heart_texture, (heart_pos_x, heart_pos_y))
                else:
                    self.screen.blit(self.empty_heart_texture, (heart_pos_x, heart_pos_y))
        except:
            pass

    def draw_creative_palette(self, inv_rect, palette_x, content_y, mouse_pos):
        """Сетка всех предметов игры для креативного режима - клик берёт
        полный стек предмета в инвентарь, без затрат материалов."""
        palette_title = self.small_font.render("ВСЕ ПРЕДМЕТЫ", True, self.UI_TEXT_DIM)
        self.screen.blit(palette_title, (palette_x, content_y))
        
        cols = 5
        cell_size = 56
        cell_gap = 6
        rows_visible = 6
        
        grid_y = content_y + 26
        grid_width = cols * (cell_size + cell_gap) - cell_gap
        
        total_items = len(self.creative_palette_items)
        total_rows = max(1, math.ceil(total_items / cols))
        max_scroll_rows = max(0, total_rows - rows_visible)
        self.max_creative_palette_scroll = max_scroll_rows
        self.creative_palette_scroll = max(0, min(self.creative_palette_scroll, max_scroll_rows))
        
        start_row = self.creative_palette_scroll
        start_index = start_row * cols
        end_index = min(total_items, start_index + rows_visible * cols)
        
        self.creative_palette_rects = []
        for i in range(start_index, end_index):
            item_id = self.creative_palette_items[i]
            row_in_view = (i - start_index) // cols
            col = (i - start_index) % cols
            cell_rect = pygame.Rect(palette_x + col * (cell_size + cell_gap), grid_y + row_in_view * (cell_size + cell_gap), cell_size, cell_size)
            hover = cell_rect.collidepoint(mouse_pos)
            self.draw_ui_slot(cell_rect, item_id, 1, hover)
            self.creative_palette_rects.append((item_id, cell_rect))
        
        grid_height = rows_visible * (cell_size + cell_gap) - cell_gap
        
        # Скроллбар справа от палитры
        if max_scroll_rows > 0:
            track_x = palette_x + grid_width + 14
            track_rect = pygame.Rect(track_x, grid_y, 6, grid_height)
            pygame.draw.rect(self.screen, (18, 19, 24), track_rect, border_radius=3)
            thumb_h = max(20, int(track_rect.height * (rows_visible / total_rows)))
            ratio = self.creative_palette_scroll / max_scroll_rows
            thumb_y = track_rect.y + int((track_rect.height - thumb_h) * ratio)
            pygame.draw.rect(self.screen, self.UI_ACCENT, (track_x, thumb_y, 6, thumb_h), border_radius=3)
        
        # Подсказка с названием предмета под курсором
        for item_id, cell_rect in self.creative_palette_rects:
            if cell_rect.collidepoint(mouse_pos):
                name = self.get_item_name(item_id)
                tip_surf = self.small_font.render(name, True, self.UI_TEXT)
                tip_bg = pygame.Surface((tip_surf.get_width() + 16, tip_surf.get_height() + 10), pygame.SRCALPHA)
                pygame.draw.rect(tip_bg, (*self.UI_BG_LIGHT, 235), (0, 0, tip_bg.get_width(), tip_bg.get_height()), border_radius=6)
                tip_x = min(cell_rect.right, inv_rect.right - tip_bg.get_width() - 8)
                self.screen.blit(tip_bg, (tip_x, cell_rect.y - tip_bg.get_height() - 4))
                self.screen.blit(tip_surf, (tip_x + 8, cell_rect.y - tip_bg.get_height() - 4 + 5))
                break

    def take_creative_item(self, item_id):
        """Кладёт полный стек предмета в первый свободный/подходящий слот
        хотбара, затем инвентаря - бесплатно, только в креативном режиме."""
        stack_size = 64
        for i in range(self.hotbar_slots):
            if self.hotbar[i] == item_id and self.hotbar_counts[i] < stack_size:
                self.hotbar_counts[i] = stack_size
                return
        for i in range(self.hotbar_slots):
            if self.hotbar[i] is None:
                self.hotbar[i] = item_id
                self.hotbar_counts[i] = stack_size
                return
        for i in range(self.inventory_slots):
            if self.inventory[i] == item_id and self.inventory_counts[i] < stack_size:
                self.inventory_counts[i] = stack_size
                return
        for i in range(self.inventory_slots):
            if self.inventory[i] is None:
                self.inventory[i] = item_id
                self.inventory_counts[i] = stack_size
                return

    def draw_inventory_ui(self):
        try:
            overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            overlay.fill((0, 0, 0, 210))
            self.screen.blit(overlay, (0, 0))
            
            inv_width, inv_height = min(980, int(WIDTH * 0.96)), min(640, int(HEIGHT * 0.88))
            inv_x, inv_y = (WIDTH - inv_width) // 2, (HEIGHT - inv_height) // 2
            inv_rect = pygame.Rect(inv_x, inv_y, inv_width, inv_height)
            mouse_pos = pygame.mouse.get_pos()
            
            self.draw_ui_panel(inv_rect, "ИНВЕНТАРЬ")
            self.draw_ui_close_button(pygame.Rect(inv_rect.right - 46, inv_rect.y + 12, 34, 34))
            self.close_btn_rect = pygame.Rect(inv_rect.right - 46, inv_rect.y + 12, 34, 34)
            
            left_x = inv_x + 28
            content_y = inv_y + 84
            
            hotbar_title = self.small_font.render("БЫСТРЫЙ ДОСТУП", True, self.UI_TEXT_DIM)
            self.screen.blit(hotbar_title, (left_x, content_y))
            
            slot_size, slot_gap = 58, 8
            hotbar_y = content_y + 26
            self.hotbar_slot_rects = []
            for i in range(self.hotbar_slots):
                slot_rect = pygame.Rect(left_x + i * (slot_size + slot_gap), hotbar_y, slot_size, slot_size)
                self.hotbar_slot_rects.append(slot_rect)
                hover = slot_rect.collidepoint(mouse_pos)
                self.draw_ui_slot(slot_rect, self.hotbar[i], self.hotbar_counts[i], hover)
            
            inv_title = self.small_font.render("ИНВЕНТАРЬ", True, self.UI_TEXT_DIM)
            inv_grid_y = hotbar_y + slot_size + 30
            self.screen.blit(inv_title, (left_x, inv_grid_y - 24))
            
            self.inventory_slot_rects = []
            for i in range(self.inventory_slots):
                row, col = i // 9, i % 9
                slot_rect = pygame.Rect(left_x + col * (slot_size + slot_gap), inv_grid_y + row * (slot_size + slot_gap), slot_size, slot_size)
                self.inventory_slot_rects.append(slot_rect)
                hover = slot_rect.collidepoint(mouse_pos)
                self.draw_ui_slot(slot_rect, self.inventory[i], self.inventory_counts[i], hover)
            
            # Разделительная линия между инвентарём и крафтом/палитрой
            divider_x = inv_x + 620
            pygame.draw.line(self.screen, self.UI_BORDER, (divider_x, content_y), (divider_x, inv_rect.bottom - 70), 2)
            
            craft_x = divider_x + 24
            
            if self.game_mode == "CREATIVE":
                self.draw_creative_palette(inv_rect, craft_x, content_y, mouse_pos)
            else:
                craft_title = self.small_font.render("КРАФТ 2×2", True, self.UI_TEXT_DIM)
                self.screen.blit(craft_title, (craft_x, content_y))
                
                recipes_per_page = 5
                self.max_inventory_recipes_scroll = max(0, len(self.inventory_recipes) - recipes_per_page)
                
                craft_y = content_y + 26
                card_w = inv_rect.right - 24 - craft_x - 20
                card_h = 68
                card_gap = 8
                
                self.craft_buttons = []
                start_index = self.inventory_recipes_scroll
                end_index = min(start_index + recipes_per_page, len(self.inventory_recipes))
                
                for i in range(start_index, end_index):
                    recipe = self.inventory_recipes[i]
                    key, name, required, result, count, description = recipe
                    can_craft = self.can_craft(required)
                    
                    btn_rect = pygame.Rect(craft_x, craft_y + (i - start_index) * (card_h + card_gap), card_w, card_h)
                    self.craft_buttons.append((key, btn_rect, recipe))
                    hover = btn_rect.collidepoint(mouse_pos)
                    
                    if can_craft:
                        color = (48, 82, 50) if not hover else (58, 98, 60)
                        border = self.UI_GOOD
                    else:
                        color = (50, 47, 45) if not hover else (58, 55, 52)
                        border = (86, 80, 76)
                    pygame.draw.rect(self.screen, color, btn_rect, border_radius=8)
                    pygame.draw.rect(self.screen, border, btn_rect, 2, border_radius=8)
                    
                    icon_rect = pygame.Rect(btn_rect.x + 6, btn_rect.y + 6, card_h - 12, card_h - 12)
                    pygame.draw.rect(self.screen, (24, 22, 20), icon_rect, border_radius=6)
                    if result in self.textures:
                        icon = pygame.transform.scale(self.textures[result], (icon_rect.width - 6, icon_rect.height - 6))
                        self.screen.blit(icon, (icon_rect.x + 3, icon_rect.y + 3))
                    
                    text_x = icon_rect.right + 10
                    max_text_w = btn_rect.right - 10 - text_x
                    name_color = self.UI_TEXT if can_craft else self.UI_TEXT_DIM
                    full_label = f"{name} ×{count}"
                    name_text = self.small_font.render(full_label, True, name_color)
                    if name_text.get_width() > max_text_w:
                        # Обрезаем по буквам с многоточием, чтобы текст не вылезал за карточку
                        truncated = full_label
                        while truncated and self.small_font.size(truncated + "…")[0] > max_text_w:
                            truncated = truncated[:-1]
                        name_text = self.small_font.render(truncated + "…", True, name_color)
                    self.screen.blit(name_text, (text_x, btn_rect.y + 8))
                    if not can_craft:
                        lock_text = self.small_font.render("нет материалов", True, self.UI_BAD)
                        self.screen.blit(lock_text, (text_x, btn_rect.y + 34))
                
                # Компактный скроллбар справа от карточек крафта
                if len(self.inventory_recipes) > recipes_per_page:
                    track_x = inv_rect.right - 24
                    track_rect = pygame.Rect(track_x, craft_y, 6, recipes_per_page * (card_h + card_gap) - card_gap)
                    pygame.draw.rect(self.screen, (18, 19, 24), track_rect, border_radius=3)
                    thumb_h = max(20, int(track_rect.height * (recipes_per_page / len(self.inventory_recipes))))
                    ratio = (self.inventory_recipes_scroll / self.max_inventory_recipes_scroll) if self.max_inventory_recipes_scroll > 0 else 0
                    thumb_y = track_rect.y + int((track_rect.height - thumb_h) * ratio)
                    pygame.draw.rect(self.screen, self.UI_ACCENT, (track_x, thumb_y, 6, thumb_h), border_radius=3)
                
                up_enabled = self.inventory_recipes_scroll > 0
                down_enabled = self.inventory_recipes_scroll < self.max_inventory_recipes_scroll
                scroll_up_rect = pygame.Rect(craft_x, craft_y - 30, 90, 22)
                scroll_down_rect = pygame.Rect(craft_x, craft_y + recipes_per_page * (card_h + card_gap), 90, 22)
                self.draw_ui_button(scroll_up_rect, "▲ вверх", up_enabled, self.small_font)
                self.draw_ui_button(scroll_down_rect, "▼ вниз", down_enabled, self.small_font)
                self.scroll_up_btn = scroll_up_rect
                self.scroll_down_btn = scroll_down_rect
                
                if self.recipe_hover_info is not None:
                    self.draw_recipe_tooltip()
            
            hints_y = inv_rect.bottom - 30
            hint = self.small_font.render("ЛКМ — взять  ·  ПКМ — половину  ·  Q — выбросить  ·  Колесико — прокрутка", True, self.UI_TEXT_DIM)
            self.screen.blit(hint, (inv_rect.centerx - hint.get_width()//2, hints_y))
        except:
            pass

    def draw_recipe_tooltip(self):
        if self.recipe_hover_info is None:
            return
            
        try:
            key, name, required, result, count, description = self.recipe_hover_info
            mx, my = pygame.mouse.get_pos()
            
            tooltip_width = 300
            tooltip_height = 200
            tooltip_x = min(mx + 10, WIDTH - tooltip_width - 10)
            tooltip_y = min(my + 10, HEIGHT - tooltip_height - 10)
            
            tooltip_surf = pygame.Surface((tooltip_width, tooltip_height), pygame.SRCALPHA)
            tooltip_surf.fill((40, 40, 40, 230))
            pygame.draw.rect(tooltip_surf, (100, 100, 100), (0, 0, tooltip_width, tooltip_height), 2)
            
            title_text = self.font.render(name, True, (255, 255, 0))
            tooltip_surf.blit(title_text, (10, 10))
            
            desc_lines = []
            words = description.split()
            current_line = ""
            for word in words:
                if len(current_line) + len(word) + 1 <= 35:
                    current_line += " " + word if current_line else word
                else:
                    desc_lines.append(current_line)
                    current_line = word
            if current_line:
                desc_lines.append(current_line)
            
            for i, line in enumerate(desc_lines):
                desc_text = self.small_font.render(line, True, (220, 220, 220))
                tooltip_surf.blit(desc_text, (10, 50 + i * 20))
            
            resources_y = 50 + len(desc_lines) * 20 + 10
            resources_text = self.small_font.render("Нужно:", True, (200, 200, 200))
            tooltip_surf.blit(resources_text, (10, resources_y))
            
            resource_y = resources_y + 25
            for item_id, amount in required.items():
                item_name = self.get_item_name(item_id)
                resource_line = f"  {item_name}: {amount} шт."
                resource_text = self.small_font.render(resource_line, True, (180, 180, 180))
                tooltip_surf.blit(resource_text, (10, resource_y))
                resource_y += 20
            
            self.screen.blit(tooltip_surf, (tooltip_x, tooltip_y))
        except:
            pass

    def get_item_name(self, item_id):
        item_names = {
            GRASS: "Трава", DIRT: "Земля", STONE: "Камень", WOOD: "Дерево",
            PLANK: "Доски", PINE_PLANK: "Еловые доски",
            STICK: "Палки", CRAFTING_TABLE: "Верстак",
            WOODEN_PICKAXE: "Деревянная кирка", WOODEN_AXE: "Деревянный топор",
            WOODEN_SWORD: "Деревянный меч", STONE_PICKAXE: "Каменная кирка",
            STONE_AXE: "Каменный топор", STONE_SWORD: "Каменный меч",
            SAND: "Песок", LEAVES: "Листья", PINE_LOG: "Ель",
            PINE_LEAVES: "Хвоя", SNOW_GRASS: "Снег", ASH: "Пепел", 
            CACTUS: "Кактус", GLASS: "Стекло", WOODEN_DOOR: "Дерев. дверь",
            PINE_DOOR: "Еловая дверь",
            FURNACE: "Печка",
            COAL_ORE: "Угольная руда", IRON_ORE: "Железная руда",
            GOLD_ORE: "Золотая руда",
            COAL: "Уголь", IRON_INGOT: "Железный слиток",
            GOLD_INGOT: "Золотой слиток", DIAMOND: "Алмаз",
            IRON_PICKAXE: "Железная кирка", IRON_AXE: "Железный топор",
            IRON_SWORD: "Железный меч", GOLD_PICKAXE: "Золотая кирка",
            GOLD_AXE: "Золотой топор", GOLD_SWORD: "Золотой меч",
            DIAMOND_PICKAXE: "Алмазная кирка", DIAMOND_AXE: "Алмазный топор",
            DIAMOND_SWORD: "Алмазный меч", STONE_BRICK: "Каменный кирпич",
            IRON_BLOCK: "Железный блок", GOLD_BLOCK: "Золотой блок",
            DIAMOND_BLOCK: "Алмазный блок", TORCH: "Факел",
            PINE_WOOD: "Еловая древесина"
        }
        return item_names.get(item_id, f"Предмет {item_id}")

    def draw_crafting_table_ui(self):
        try:
            overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            overlay.fill((0, 0, 0, 210))
            self.screen.blit(overlay, (0, 0))
            
            table_width, table_height = min(680, int(WIDTH * 0.95)), min(700, int(HEIGHT * 0.9))
            table_x, table_y = (WIDTH - table_width) // 2, (HEIGHT - table_height) // 2
            table_rect = pygame.Rect(table_x, table_y, table_width, table_height)
            mouse_pos = pygame.mouse.get_pos()
            
            self.draw_ui_panel(table_rect, "ВЕРСТАК")
            close_rect = pygame.Rect(table_rect.right - 46, table_y + 12, 34, 34)
            self.draw_ui_close_button(close_rect)
            self.crafting_close_btn = close_rect
            
            recipes_per_page = 6
            self.max_crafting_recipes_scroll = max(0, len(self.crafting_table_recipes) - recipes_per_page)
            
            list_x = table_x + 24
            list_y = table_y + 84
            list_width = table_width - 48 - 28
            card_height = 84
            card_gap = 10
            
            self.crafting_table_buttons = []
            
            start_index = self.crafting_recipes_scroll
            end_index = min(start_index + recipes_per_page, len(self.crafting_table_recipes))
            
            for i in range(start_index, end_index):
                recipe = self.crafting_table_recipes[i]
                key, name, required, result, count, description = recipe
                
                can_craft = self.can_craft(required)
                
                card_y = list_y + (i - start_index) * (card_height + card_gap)
                btn_rect = pygame.Rect(list_x, card_y, list_width, card_height)
                self.crafting_table_buttons.append((key, btn_rect, recipe))
                
                hover = btn_rect.collidepoint(mouse_pos)
                if can_craft:
                    base_color = (44, 74, 46) if not hover else (52, 88, 54)
                    border_color = self.UI_GOOD
                else:
                    base_color = (44, 42, 40) if not hover else (52, 49, 47)
                    border_color = (86, 80, 76)
                
                pygame.draw.rect(self.screen, base_color, btn_rect, border_radius=10)
                pygame.draw.rect(self.screen, border_color, btn_rect, 2, border_radius=10)
                
                icon_bg = pygame.Rect(btn_rect.x + 10, btn_rect.centery - 28, 56, 56)
                pygame.draw.rect(self.screen, (20, 21, 26), icon_bg, border_radius=10)
                if result in self.textures:
                    icon = pygame.transform.scale(self.textures[result], (44, 44))
                    self.screen.blit(icon, (icon_bg.centerx - 22, icon_bg.centery - 22))
                
                text_x = icon_bg.right + 14
                name_color = self.UI_TEXT if can_craft else self.UI_TEXT_DIM
                name_text = self.font.render(f"{name}", True, name_color)
                self.screen.blit(name_text, (text_x, btn_rect.y + 10))
                
                count_text = self.small_font.render(f"×{count}", True, self.UI_ACCENT)
                self.screen.blit(count_text, (text_x, btn_rect.y + 38))
                
                if not can_craft:
                    lock_text = self.small_font.render("Не хватает материалов", True, self.UI_BAD)
                    self.screen.blit(lock_text, (text_x, btn_rect.bottom - 24))
            
            # Полоса-индикатор прокрутки справа от списка
            track_x = list_x + list_width + 14
            track_rect = pygame.Rect(track_x, list_y, 6, recipes_per_page * (card_height + card_gap) - card_gap)
            pygame.draw.rect(self.screen, (18, 19, 24), track_rect, border_radius=3)
            
            total_recipes = max(1, len(self.crafting_table_recipes))
            thumb_h = max(24, int(track_rect.height * (recipes_per_page / total_recipes)))
            scroll_ratio = (self.crafting_recipes_scroll / self.max_crafting_recipes_scroll) if self.max_crafting_recipes_scroll > 0 else 0
            thumb_y = track_rect.y + int((track_rect.height - thumb_h) * scroll_ratio)
            pygame.draw.rect(self.screen, self.UI_ACCENT, (track_x, thumb_y, 6, thumb_h), border_radius=3)
            
            scroll_up_rect = pygame.Rect(track_x - 12, list_y - 28, 32, 22)
            scroll_down_rect = pygame.Rect(track_x - 12, list_y + track_rect.height + 6, 32, 22)
            up_enabled = self.crafting_recipes_scroll > 0
            down_enabled = self.crafting_recipes_scroll < self.max_crafting_recipes_scroll
            self.draw_ui_button(scroll_up_rect, "▲", up_enabled, self.small_font)
            self.draw_ui_button(scroll_down_rect, "▼", down_enabled, self.small_font)
            self.craft_scroll_up_btn = scroll_up_rect
            self.craft_scroll_down_btn = scroll_down_rect
            
            hints_y = table_rect.bottom - 30
            hint1 = self.small_font.render("ЛКМ — скрафтить  ·  Колесико — прокрутка", True, self.UI_TEXT_DIM)
            self.screen.blit(hint1, (table_rect.centerx - hint1.get_width()//2, hints_y))
        except:
            pass

    def draw_hud(self):
        try:
            self.draw_health()
            
            # Полупрозрачная плашка сверху-слева (мир, время, день/ночь бар)
            top_left_bg = pygame.Surface((260, 110), pygame.SRCALPHA)
            pygame.draw.rect(top_left_bg, (*self.UI_BG, 160), (0, 0, 260, 110), border_radius=10)
            self.screen.blit(top_left_bg, (12, 12))
            
            world_info = self.small_font.render(f"Мир: {self.current_world_name}", True, self.UI_TEXT)
            self.screen.blit(world_info, (24, 20))
            
            time_text = "День" if not self.is_night else "Ночь"
            time_color = self.UI_ACCENT if not self.is_night else (140, 150, 220)
            time_surface = self.small_font.render(f"Время: {time_text}", True, time_color)
            self.screen.blit(time_surface, (24, 46))
            
            if self.day_night_cycle:
                day_time_seconds = self.day_time_ticks / FPS
                day_progress = day_time_seconds / self.day_duration
                bar_width = 220
                bar_height = 8
                bar_x = 24
                bar_y = 76
                
                pygame.draw.rect(self.screen, (18, 19, 24), (bar_x, bar_y, bar_width, bar_height), border_radius=4)
                
                fill_width = int(bar_width * day_progress)
                fill_color = (140, 150, 220) if self.is_night else self.UI_ACCENT
                if fill_width > 0:
                    pygame.draw.rect(self.screen, fill_color, (bar_x, bar_y, fill_width, bar_height), border_radius=4)
                
                marker_x = bar_x + int(bar_width * (60 / self.day_duration))
                pygame.draw.line(self.screen, self.UI_GOOD, (marker_x, bar_y - 4), (marker_x, bar_y + bar_height + 4), 2)
                
                marker_x = bar_x + int(bar_width * (180 / self.day_duration))
                pygame.draw.line(self.screen, self.UI_BAD, (marker_x, bar_y - 4), (marker_x, bar_y + bar_height + 4), 2)
            
            # Плашка сверху-справа (режим игры)
            mode_text = f"Режим: {self.game_mode}"
            if self.is_swimming:
                mode_text += "  ·  ПЛАВАНИЕ"
            mode_surface = self.small_font.render(mode_text, True, self.UI_TEXT)
            top_right_bg = pygame.Surface((mode_surface.get_width() + 24, 40), pygame.SRCALPHA)
            pygame.draw.rect(top_right_bg, (*self.UI_BG, 160), (0, 0, top_right_bg.get_width(), 40), border_radius=10)
            self.screen.blit(top_right_bg, (WIDTH - top_right_bg.get_width() - 12, 12))
            self.screen.blit(mode_surface, (WIDTH - top_right_bg.get_width() - 12 + 12, 24))
            
            # Подсказка для F3
            f3_hint = self.small_font.render("F3 — информация", True, self.UI_TEXT_DIM)
            self.screen.blit(f3_hint, (WIDTH - f3_hint.get_width() - 16, HEIGHT - 26))
            
            if not self.inventory_open and not self.crafting_table_open and not self.furnace_open and not self.mods_menu_open:
                controls = [
                    ("E", "Инвентарь"), ("ПКМ верстак", "Крафт"), ("ПКМ печка", "Плавка"),
                    ("1-9", "Слот"), ("Колесико", "Выбор"), ("Q", "Бросить"),
                    ("M", "Моды"), ("F3", "Дебаг"),
                ]
                if self.game_mode == "CREATIVE":
                    fly_state = "ВКЛ" if self.creative_flying else "ВЫКЛ"
                    controls.append(("F", f"Полёт: {fly_state}"))
                
                control_text = "   ·   ".join(f"{key}: {action}" for key, action in controls)
                control_surface = self.small_font.render(control_text, True, self.UI_TEXT_DIM)
                bar_bg = pygame.Surface((control_surface.get_width() + 24, 32), pygame.SRCALPHA)
                pygame.draw.rect(bar_bg, (*self.UI_BG, 140), (0, 0, bar_bg.get_width(), 32), border_radius=8)
                bar_x = WIDTH // 2 - bar_bg.get_width() // 2
                self.screen.blit(bar_bg, (bar_x, HEIGHT - 40))
                self.screen.blit(control_surface, (bar_x + 12, HEIGHT - 34))
        except:
            pass

    def draw_death_screen(self):
        if not self.show_death_screen:
            return
        
        try:
            overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            overlay.fill((0, 0, 0, 150))
            self.screen.blit(overlay, (0, 0))
            
            time_since_death = time.time() - self.death_timer
            scale = 1 + math.sin(time_since_death * 5) * 0.1
            
            death_font = pygame.font.SysFont("Arial", int(80 * scale), bold=True)
            death_text = death_font.render("ТЫ УМЕР", True, (255, 0, 0))
            
            text_shadow = death_font.render("ТЫ УМЕР", True, (100, 0, 0))
            
            text_rect = death_text.get_rect(center=(WIDTH // 2, HEIGHT // 2 - 50))
            shadow_rect = text_shadow.get_rect(center=(WIDTH // 2 + 5, HEIGHT // 2 - 45))
            
            self.screen.blit(text_shadow, shadow_rect)
            self.screen.blit(death_text, text_rect)
            
            respawn_time = max(0, 3 - time_since_death)
            timer_text = self.font.render(f"Возрождение через {respawn_time:.1f}с", True, (255, 255, 255))
            timer_rect = timer_text.get_rect(center=(WIDTH // 2, HEIGHT // 2 + 30))
            self.screen.blit(timer_text, timer_rect)
            
            skull_pos = (WIDTH // 2 - 50, HEIGHT // 2 + 80)
            pygame.draw.circle(self.screen, (200, 200, 200), skull_pos, 20)
            pygame.draw.circle(self.screen, (0, 0, 0), (skull_pos[0] - 8, skull_pos[1] - 5), 3)
            pygame.draw.circle(self.screen, (0, 0, 0), (skull_pos[0] + 8, skull_pos[1] - 5), 3)
        except:
            pass

    def get_scaled_liquid_surface(self, b_id, h_int):
        """Возвращает поверхность жидкости, масштабированную под текущий
        визуальный уровень (h_int пикселей высоты), из кэша - без него
        pygame.transform.scale вызывался бы заново на каждый видимый тайл
        воды/лавы каждый кадр, что было заметной нагрузкой на рендер."""
        key = (b_id, h_int)
        cached = self._liquid_surf_cache.get(key)
        if cached is None:
            cached = pygame.transform.scale(self.textures[b_id], (TILE_SIZE, h_int))
            self._liquid_surf_cache[key] = cached
        return cached

    def draw_door(self, b_id, rx, ry, door_data):
        try:
            door_id, is_open = door_data
            
            if is_open:
                if door_id == WOODEN_DOOR:
                    texture_key = "wooden_door_open"
                elif door_id == PINE_DOOR:
                    texture_key = "pine_door_open"
                else:  # IRON_DOOR
                    texture_key = "iron_door_open"
            else:
                if door_id == WOODEN_DOOR:
                    texture_key = "wooden_door_closed"
                elif door_id == PINE_DOOR:
                    texture_key = "pine_door_closed"
                else:  # IRON_DOOR
                    texture_key = "iron_door_closed"
            
            if texture_key in self.door_textures and self.door_textures[texture_key] is not None:
                texture = self.door_textures[texture_key]
                self.screen.blit(texture, (rx, ry - TILE_SIZE))
            else:
                # Fallback если текстура не загружена
                fallback = pygame.Surface((TILE_SIZE, TILE_SIZE * 2))
                if is_open:
                    fallback.fill((200, 200, 200, 128))
                else:
                    fallback.fill((100, 100, 100))
                self.screen.blit(fallback, (rx, ry - TILE_SIZE))
        except:
            pass

    def draw_torch(self, b_id, rx, ry):
        try:
            if b_id in self.textures:
                self.screen.blit(self.textures[b_id], (rx + TILE_SIZE // 4, ry))
        except:
            pass

    def draw_player(self):
        try:
            rx, ry = self.player_rect.x - self.camera_x, self.player_rect.y - self.camera_y
            
            is_player_underground = False
            player_x = int(self.player_rect.centerx // TILE_SIZE)
            player_y = int(self.player_rect.centery // TILE_SIZE)
            
            if player_y > 0 and (player_x, player_y - 1) in self.world:
                block_id = self.world[(player_x, player_y - 1)][0]
                if block_id not in self.non_solid_blocks and block_id != TORCH and block_id != GLASS:
                    is_player_underground = True
            
            if self.player_facing == "right":
                if self.is_swimming:
                    player_texture = self.player_water_texture_right
                else:
                    player_texture = self.player_texture_right
            else:
                if self.is_swimming:
                    player_texture = self.player_water_texture_left
                else:
                    player_texture = self.player_texture_left
            
            if is_player_underground:
                dark_texture = player_texture.copy()
                dark_texture.set_alpha(150)
                self.screen.blit(dark_texture, (rx, ry))
            else:
                self.screen.blit(player_texture, (rx, ry))
        except:
            pass

    def draw_world_select(self):
        try:
            self.screen.fill((22, 24, 30))
            mouse_pos = pygame.mouse.get_pos()
            
            title = self.font.render("ВЫБОР МИРА", True, self.UI_ACCENT)
            self.screen.blit(title, (WIDTH // 2 - title.get_width() // 2, 50))
            
            worlds_per_page = 5
            start_index = max(0, self.world_select_index - 2)
            end_index = min(len(self.worlds_list), start_index + worlds_per_page)
            
            world_area = pygame.Rect(WIDTH // 2 - 300, 150, 600, 400)
            pygame.draw.rect(self.screen, self.UI_BG, world_area, border_radius=self.UI_RADIUS)
            pygame.draw.rect(self.screen, self.UI_BORDER, world_area, 2, border_radius=self.UI_RADIUS)
            
            if len(self.worlds_list) == 0:
                no_worlds = self.font.render("Нет сохранённых миров", True, self.UI_TEXT_DIM)
                self.screen.blit(no_worlds, (world_area.centerx - no_worlds.get_width() // 2, world_area.centery))
            else:
                for i in range(start_index, end_index):
                    world = self.worlds_list[i]
                    world_y = 180 + (i - start_index) * 70
                    
                    world_rect = pygame.Rect(WIDTH // 2 - 280, world_y, 560, 60)
                    selected = i == self.world_select_index
                    bg = (58, 62, 80) if selected else self.UI_SLOT
                    border = self.UI_ACCENT if selected else self.UI_SLOT_BORDER
                    pygame.draw.rect(self.screen, bg, world_rect, border_radius=8)
                    pygame.draw.rect(self.screen, border, world_rect, 2, border_radius=8)
                    
                    name_text = self.font.render(world['name'], True, self.UI_TEXT)
                    self.screen.blit(name_text, (world_rect.x + 20, world_rect.y + 10))
                    
                    info_text = self.small_font.render(f"Тип: {world['world_type']}  ·  Последняя игра: {world['last_played']}", True, self.UI_TEXT_DIM)
                    self.screen.blit(info_text, (world_rect.x + 20, world_rect.y + 36))
            
            btn_y = world_area.bottom + 30
            
            create_btn = pygame.Rect(WIDTH // 2 - 280, btn_y, 180, 50)
            self.draw_ui_button(create_btn, "Создать мир", True, self.small_font)
            
            delete_btn = pygame.Rect(WIDTH // 2 - 80, btn_y, 180, 50)
            self.draw_ui_button(delete_btn, "Удалить мир", len(self.worlds_list) > 0, self.small_font)
            
            mods_btn = pygame.Rect(WIDTH // 2 + 120, btn_y, 160, 50)
            self.draw_ui_button(mods_btn, "Моды", True, self.small_font)
            
            back_btn = pygame.Rect(WIDTH // 2 + 300, btn_y, 160, 50)
            self.draw_ui_button(back_btn, "Назад", True, self.small_font)
            
            hint_text = self.small_font.render("Стрелки Вверх/Вниз — выбор мира  ·  Enter или ЛКМ — войти", True, self.UI_TEXT_DIM)
            self.screen.blit(hint_text, (WIDTH // 2 - hint_text.get_width() // 2, HEIGHT - 40))
        except:
            pass

    def draw_world_create(self):
        try:
            self.screen.fill((22, 24, 30))
            
            title = self.font.render("СОЗДАНИЕ МИРА", True, self.UI_ACCENT)
            self.screen.blit(title, (WIDTH // 2 - title.get_width() // 2, 50))
            
            create_area = pygame.Rect(WIDTH // 2 - 300, 150, 600, 380)
            pygame.draw.rect(self.screen, self.UI_BG, create_area, border_radius=self.UI_RADIUS)
            pygame.draw.rect(self.screen, self.UI_BORDER, create_area, 2, border_radius=self.UI_RADIUS)
            
            name_text = self.small_font.render("НАЗВАНИЕ МИРА", True, self.UI_TEXT_DIM)
            self.screen.blit(name_text, (create_area.x + 50, create_area.y + 34))
            
            name_input = pygame.Rect(create_area.x + 50, create_area.y + 60, 500, 50)
            input_border = self.UI_ACCENT if self.typing_name else self.UI_SLOT_BORDER
            pygame.draw.rect(self.screen, self.UI_SLOT, name_input, border_radius=8)
            pygame.draw.rect(self.screen, input_border, name_input, 2, border_radius=8)
            
            display_name = self.world_create_name
            if self.typing_name and time.time() % 1 > 0.5:
                display_name += "|"
            
            name_display = self.font.render(display_name, True, self.UI_TEXT)
            self.screen.blit(name_display, (name_input.x + 12, name_input.y + 12))
            
            type_text = self.small_font.render("ТИП МИРА", True, self.UI_TEXT_DIM)
            self.screen.blit(type_text, (create_area.x + 50, create_area.y + 138))
            
            limited_btn = pygame.Rect(create_area.x + 50, create_area.y + 164, 240, 50)
            infinite_btn = pygame.Rect(create_area.x + 310, create_area.y + 164, 240, 50)
            
            self.draw_type_choice_button(limited_btn, "Ограниченный", self.world_type == "LIMITED")
            self.draw_type_choice_button(infinite_btn, "Бесконечный", self.world_type == "INFINITE")
            
            mode_text = self.small_font.render("РЕЖИМ ИГРЫ", True, self.UI_TEXT_DIM)
            self.screen.blit(mode_text, (create_area.x + 50, create_area.y + 242))
            
            survival_btn = pygame.Rect(create_area.x + 50, create_area.y + 268, 240, 50)
            creative_btn = pygame.Rect(create_area.x + 310, create_area.y + 268, 240, 50)
            
            self.draw_type_choice_button(survival_btn, "Выживание", self.world_create_mode == "SURVIVAL")
            self.draw_type_choice_button(creative_btn, "Креатив", self.world_create_mode == "CREATIVE")
            
            mode_note = self.small_font.render("Режим нельзя будет сменить после создания мира", True, self.UI_TEXT_DIM)
            self.screen.blit(mode_note, (create_area.x + 50, create_area.y + 324))
            
            btn_y = create_area.bottom + 30
            
            create_btn = pygame.Rect(WIDTH // 2 - 140, btn_y, 130, 50)
            self.draw_ui_button(create_btn, "Создать", True, self.small_font)
            
            cancel_btn = pygame.Rect(WIDTH // 2 + 20, btn_y, 130, 50)
            self.draw_ui_button(cancel_btn, "Отмена", True, self.small_font)
            
            hint_text = self.small_font.render("Введите название мира и выберите тип и режим", True, self.UI_TEXT_DIM)
            self.screen.blit(hint_text, (WIDTH // 2 - hint_text.get_width() // 2, HEIGHT - 40))
        except:
            pass

    def draw_main_menu(self):
        try:
            # Мягкий вертикальный градиент вместо плоской заливки
            top_color = (18, 20, 26)
            bottom_color = (32, 35, 44)
            for y in range(0, HEIGHT, 4):
                ratio = y / HEIGHT
                r = int(top_color[0] + (bottom_color[0] - top_color[0]) * ratio)
                g = int(top_color[1] + (bottom_color[1] - top_color[1]) * ratio)
                b = int(top_color[2] + (bottom_color[2] - top_color[2]) * ratio)
                pygame.draw.rect(self.screen, (r, g, b), (0, y, WIDTH, 4))
            
            title = self.big_font.render("TERAFLAT", True, self.UI_ACCENT)
            subtitle = self.menu_font.render("2D", True, self.UI_TEXT_DIM)
            self.screen.blit(title, (WIDTH // 2 - title.get_width() // 2, 100))
            self.screen.blit(subtitle, (WIDTH // 2 - subtitle.get_width() // 2, 170))
            
            center_x = WIDTH // 2
            btn_width, btn_height = 300, 60
            btn_y_start = 280
            
            single_btn = pygame.Rect(center_x - btn_width // 2, btn_y_start, btn_width, btn_height)
            multi_btn = pygame.Rect(center_x - btn_width // 2, btn_y_start + 80, btn_width, btn_height)
            mods_btn = pygame.Rect(center_x - btn_width // 2, btn_y_start + 160, btn_width, btn_height)
            quit_btn = pygame.Rect(center_x - btn_width // 2, btn_y_start + 240, btn_width, btn_height)
            
            self.draw_ui_button(single_btn, "ОДИНОЧНАЯ ИГРА", True, self.menu_font)
            self.draw_ui_button(multi_btn, "СЕТЕВАЯ ИГРА", False, self.menu_font)
            
            coming_soon = self.small_font.render("(скоро)", True, self.UI_BAD)
            self.screen.blit(coming_soon, (multi_btn.right - coming_soon.get_width() - 10, multi_btn.top + 8))
            
            self.draw_ui_button(mods_btn, "МОДЫ", True, self.menu_font)
            self.draw_ui_button(quit_btn, "ВЫЙТИ", True, self.menu_font)
            
            version_text = self.small_font.render("Версия 0.1  ·  FPS: " + str(int(self.clock.get_fps())), True, self.UI_TEXT_DIM)
            self.screen.blit(version_text, (10, HEIGHT - 30))
            
            # Диагностика ресурсов: показываем только если чего-то не хватает
            n_tex = _count_files("Textures")
            n_mus = _count_files("Music")
            if n_tex <= 0 or n_mus <= 0:
                diag = self.small_font.render(
                    f"Textures: {n_tex} файлов, Music: {n_mus} файлов  |  папка: {os.getcwd()}",
                    True, self.UI_BAD)
                self.screen.blit(diag, (10, HEIGHT - 60))
        except:
            pass

    def draw(self):
        try:
            if self.state == "MAIN_MENU":
                self.draw_main_menu()
            elif self.state == "WORLD_SELECT":
                self.draw_world_select()
            elif self.state == "WORLD_CREATE":
                self.draw_world_create()
            elif self.state == "PLAYING":
                px_tile = int(self.player_rect.centerx // TILE_SIZE)
                
                if self.is_night:
                    target_sky = [20, 20, 40]
                else:
                    if self.get_biome(px_tile) == "ASH": 
                        target_sky = [100, 30, 30]
                    elif self.get_biome(px_tile) == "DESERT":
                        target_sky = [255, 200, 100]
                    else:
                        target_sky = [135, 206, 250]
                
                for i in range(3): 
                    self.sky_color[i] += (target_sky[i] - self.sky_color[i]) * 0.05
                    
                self.screen.fill(self.sky_color)
                
                # Оптимизация рендеринга: рендерим только видимые чанки
                sx, sy = int(self.camera_x//40), int(self.camera_y//40)
                render_start_x = max(0, sx - 1) if self.world_type == "LIMITED" else sx - 1
                render_end_x = min(sx + (WIDTH//40) + 2, 301) if self.world_type == "LIMITED" else sx + (WIDTH//40) + 2
                
                # Кэширование рендера (упрощенное)
                current_time = time.time()
                if current_time - self.last_render_time > self.render_cache_duration:
                    self.render_cache.clear()
                    self.last_render_time = current_time
                
                view_box = self.get_view_tile_box()
                render_start_x = max(render_start_x, view_box[0])
                render_end_x = min(render_end_x, view_box[2])
                render_y0 = max(sy - 1, view_box[1])
                render_y1 = min(sy + (HEIGHT//40) + 2, view_box[3])
                
                for x in range(render_start_x, render_end_x):
                    for y in range(render_y0, render_y1):
                        if (x, y) in self.world:
                            b_id, lvl, is_f = self.world[(x, y)]
                            if b_id != EMPTY:
                                rx, ry = x*40 - self.camera_x, y*40 - self.camera_y
                                
                                # Проверка на видимость
                                if rx < -40 or rx > WIDTH or ry < -40 or ry > HEIGHT:
                                    continue
                                
                                if b_id in [WOODEN_DOOR, PINE_DOOR]:
                                    if (x, y) in self.door_states:
                                        self.draw_door(b_id, rx, ry, self.door_states[(x, y)])
                                    else:
                                        self.screen.blit(self.textures[b_id], (rx, ry - TILE_SIZE))
                                elif b_id == GLASS:
                                    if b_id in self.textures:
                                        self.screen.blit(self.textures[b_id], (rx, ry))
                                elif b_id == TORCH:
                                    self.draw_torch(b_id, rx, ry)
                                elif b_id in (CRAFTING_TABLE, FURNACE) and b_id in self.textures:
                                    # Верстак 2x1 (вправо от клетки), печка 1x2 (вверх от клетки).
                                    # Физически - одна клетка, как у двери.
                                    tex = self.textures[b_id]
                                    if self.is_mining and self.mining_target == (x, y):
                                        tex = tex.copy()
                                        tex.set_alpha(128)
                                    if b_id == FURNACE:
                                        self.screen.blit(tex, (rx, ry - TILE_SIZE))
                                    else:
                                        self.screen.blit(tex, (rx, ry))
                                elif self.is_mining and self.mining_target == (x, y):
                                    if b_id in self.textures:
                                        texture = self.textures[b_id].copy()
                                        texture.set_alpha(128)
                                        self.screen.blit(texture, (rx, ry))
                                    elif b_id in [WATER, LAVA]:
                                        if self.world.get((x, y-1), [0])[0] == b_id:
                                            h = 40
                                        else:
                                            h = 40 * ((lvl + 1) / 8)
                                        surf = self.get_scaled_liquid_surface(b_id, int(h)).copy()
                                        surf.set_alpha(128)
                                        self.screen.blit(surf, (rx, ry + (40 - h)))
                                else:
                                    if b_id in [WATER, LAVA]:
                                        if self.world.get((x, y-1), [0])[0] == b_id:
                                            h = 40
                                        else:
                                            h = 40 * ((lvl + 1) / 8)
                                        surf = self.get_scaled_liquid_surface(b_id, int(h))
                                        self.screen.blit(surf, (rx, ry + (40 - h)))
                                    else: 
                                        self.screen.blit(self.textures[b_id], (rx, ry))
                
                # Оптимизация: рендерим только предметы вблизи игрока
                player_screen_x = self.player_rect.centerx - self.camera_x
                player_screen_y = self.player_rect.centery - self.camera_y
                
                for item in self.dropped_items:
                    item_screen_x = item.x - self.camera_x
                    item_screen_y = item.y - self.camera_y
                    
                    # Проверяем, находится ли предмет рядом с игроком
                    if abs(item_screen_x - player_screen_x) < WIDTH + 100 and abs(item_screen_y - player_screen_y) < HEIGHT + 100:
                        item.draw(self.screen, self.textures, self.camera_x, self.camera_y)
                
                self.draw_player()
                
                # Оптимизация частиц
                if len(self.ash_particles) > 50:
                    self.ash_particles = self.ash_particles[-50:]
                
                if self.graphics_quality > 0:
                    for p in self.ash_particles: 
                        pygame.draw.rect(self.screen, (100, 100, 100), (p[0], p[1], 4, 4))
                
                self.draw_view_frame(view_box)
                self.apply_lighting(view_box)
                
                if self.furnace_open is not None and self.furnace_open in self.furnaces:
                    self.draw_furnace_ui(self.furnaces[self.furnace_open])
                elif self.mods_menu_open:
                    self.draw_mods_menu()
                elif not self.inventory_open and not self.crafting_table_open and self.furnace_open is None:
                    self.draw_mining_progress()
                    self.draw_hotbar()
                    self.draw_hud()
                    self.draw_mobile_controls()
                    self.draw_death_screen()
                    self.draw_debug_info()  # Добавляем отображение debug информации
                elif self.inventory_open:
                    self.draw_inventory_ui()
                    self.draw_death_screen()
                elif self.crafting_table_open:
                    self.draw_crafting_table_ui()
                    self.draw_death_screen()
                
                if self.dragging_item is not None:
                    self.draw_dragging_item()
                
                if self.paused:
                    if self.settings_open:
                        self.draw_settings_menu()
                    else:
                        self.draw_pause_menu()
        except:
            pass

    def handle_screen_resize(self, new_width, new_height):
        """Подстраивает игру под новый размер экрана/окна (поворот экрана на
        телефоне, сплит-скрин, изменение размера окна на ПК). WIDTH/HEIGHT -
        глобальные переменные модуля, которые весь остальной код уже читает
        напрямую, поэтому достаточно обновить их и пересоздать поверхности,
        которые захватили старый размер при создании."""
        global WIDTH, HEIGHT
        if new_width <= 0 or new_height <= 0:
            return
        if new_width == WIDTH and new_height == HEIGHT:
            return
        WIDTH, HEIGHT = new_width, new_height
        try:
            self.screen = pygame.display.set_mode((WIDTH, HEIGHT), pygame.RESIZABLE)
        except Exception:
            self.screen = pygame.display.get_surface()
        self.init_lighting()
        # Кэш масштабированных поверхностей жидкости не зависит от размера
        # экрана (только от TILE_SIZE и уровня жидкости), поэтому его не
        # трогаем - но координаты/размеры UI-панелей у нас везде считаются
        # заново из текущих WIDTH/HEIGHT при каждой отрисовке, так что
        # никакого дополнительного пересчёта не требуется.

    def run(self):
        running = True
        while running:
            try:
                # Экранная клавиатура (Android): включаем ввод текста только пока
                # активно текстовое поле, иначе клавиатура не появляется.
                want_text = (self.state == "WORLD_CREATE" and self.typing_name)
                if want_text != getattr(self, '_text_input_on', False):
                    try:
                        if want_text:
                            center_x = WIDTH // 2
                            pygame.key.set_text_input_rect(pygame.Rect(center_x - 250, 210, 500, 50))
                            pygame.key.start_text_input()
                        else:
                            pygame.key.stop_text_input()
                    except Exception:
                        pass
                    self._text_input_on = want_text
                
                for event in pygame.event.get():
                    if event.type == pygame.TEXTINPUT and self.state == "WORLD_CREATE" and self.typing_name:
                        for ch in event.text:
                            if len(self.world_create_name) < 20 and ch.isprintable():
                                self.world_create_name += ch
                        continue

                    if event.type == pygame.QUIT: 
                        running = False
                    
                    if event.type == pygame.VIDEORESIZE:
                        self.handle_screen_resize(event.w, event.h)
                    elif hasattr(pygame, 'WINDOWSIZECHANGED') and event.type == pygame.WINDOWSIZECHANGED:
                        self.handle_screen_resize(event.x, event.y)
                    
                    if event.type == MUSIC_END_EVENT:
                        if self.current_music_subfolder:
                            self.play_random_music(self.current_music_subfolder)
                    
                    if event.type in (pygame.FINGERDOWN, pygame.FINGERMOTION, pygame.FINGERUP) and self.state == "PLAYING":
                        self.touch_device_detected = True
                        # SDL даёт координаты пальца в долях экрана (0..1) -
                        # переводим в пиксели.
                        touch_x = event.x * WIDTH
                        touch_y = event.y * HEIGHT
                        touch_id = event.finger_id
                        
                        if event.type == pygame.FINGERDOWN:
                            L = self.get_mobile_layout()
                            pos = (touch_x, touch_y)
                            menu_open = self.mobile_menu_open()
                            
                            if L['pause'].collidepoint(pos):
                                if not self.show_death_screen:
                                    if self.paused:
                                        self.paused = False
                                    elif not (self.inventory_open or self.crafting_table_open or self.furnace_open is not None or self.mods_menu_open):
                                        self.paused = True
                            elif L['debug'].collidepoint(pos):
                                self.show_debug_info = not self.show_debug_info
                            elif L['inv'].collidepoint(pos):
                                if not self.show_death_screen and not self.paused:
                                    self.inventory_open = not self.inventory_open
                                    if not self.inventory_open:
                                        self.stop_dragging()
                            elif not menu_open and L['jump'].collidepoint(pos):
                                self.virtual_jump_btn_held = True
                                self.virtual_touch_ids[touch_id] = 'jump'
                                self.update_virtual_jump()
                            elif not menu_open and L['mode'].collidepoint(pos):
                                self.mobile_action_mode = 'place' if self.mobile_action_mode == 'mine' else 'mine'
                            elif not menu_open and L['joy_zone'].collidepoint(pos) and self.joystick_touch_id is None:
                                # Плавающий джойстик: база появляется под пальцем
                                R = self.get_joystick_radius()
                                ox = max(R + 8, min(WIDTH - R - 8, touch_x))
                                oy = max(R + 8, min(HEIGHT - R - 8, touch_y))
                                self.joystick_touch_id = touch_id
                                self.joystick_active = True
                                self.joystick_origin = (ox, oy)
                                self.joystick_pos = (ox, oy)
                                self.virtual_touch_ids[touch_id] = 'joystick'
                        
                        elif event.type == pygame.FINGERMOTION:
                            if self.virtual_touch_ids.get(touch_id) == 'joystick':
                                self.update_virtual_joystick(touch_x, touch_y)
                        
                        elif event.type == pygame.FINGERUP:
                            role = self.virtual_touch_ids.pop(touch_id, None)
                            if role == 'joystick':
                                self.joystick_active = False
                                self.joystick_touch_id = None
                                self.virtual_move_x = 0.0
                                self.virtual_stick_up = False
                                self.joystick_pos = self.joystick_origin
                                self.update_virtual_jump()
                            elif role == 'jump':
                                self.virtual_jump_btn_held = False
                                self.update_virtual_jump()
                    
                    if event.type == pygame.KEYDOWN:
                        # Новая клавиша F3 для отображения debug информации
                        if event.key == pygame.K_F3 and self.state == "PLAYING":
                            self.show_debug_info = not self.show_debug_info
                        
                        if event.key == pygame.K_ESCAPE: 
                            if self.state == "PLAYING":
                                if self.inventory_open:
                                    self.inventory_open = False
                                    self.stop_dragging()
                                elif self.crafting_table_open:
                                    self.crafting_table_open = False
                                    self.stop_dragging()
                                elif self.furnace_open is not None:
                                    self.furnace_open = None
                                    self.stop_dragging()
                                elif self.mods_menu_open:
                                    self.mods_menu_open = False
                                elif self.paused:
                                    if self.settings_open:
                                        self.settings_open = False
                                        self.dragging_slider = None
                                        self.save_settings()
                                    else:
                                        self.paused = False
                                else:
                                    self.paused = True
                            elif self.state == "WORLD_SELECT":
                                self.state = "MAIN_MENU"
                            elif self.state == "WORLD_CREATE":
                                self.state = "WORLD_SELECT"
                                self.typing_name = False
                            elif self.state == "MAIN_MENU":
                                running = False
                        
                        elif event.key == pygame.K_e and self.state == "PLAYING" and not self.show_death_screen:
                            if not self.crafting_table_open and self.furnace_open is None and not self.mods_menu_open:
                                self.inventory_open = not self.inventory_open
                                if not self.inventory_open:
                                    self.stop_dragging()
                        
                        elif event.key == pygame.K_m and self.state == "PLAYING" and not self.show_death_screen:
                            if not self.inventory_open and not self.crafting_table_open and self.furnace_open is None:
                                self.mods_menu_open = not self.mods_menu_open
                                if self.mods_menu_open:
                                    self.mod_manager.scan_mods()
                        
                        elif event.key == pygame.K_f and self.state == "PLAYING" and not self.show_death_screen:
                            if self.game_mode == "CREATIVE" and not self.inventory_open and not self.crafting_table_open and self.furnace_open is None and not self.mods_menu_open and not self.paused:
                                self.creative_flying = not self.creative_flying
                        
                        elif event.key == pygame.K_q and self.state == "PLAYING" and not self.show_death_screen:
                            if not self.inventory_open and not self.crafting_table_open and self.furnace_open is None and not self.mods_menu_open:
                                self.drop_item_from_inventory()
                        
                        elif pygame.K_1 <= event.key <= pygame.K_9 and self.state == "PLAYING": 
                            slot_index = (event.key - pygame.K_1) % 9
                            if slot_index < self.hotbar_slots:
                                self.selected_slot = slot_index
                        
                        elif event.key == pygame.K_UP and (self.state == "WORLD_SELECT" or (self.state == "PLAYING" and self.mods_menu_open)):
                            if self.state == "WORLD_SELECT" and len(self.worlds_list) > 0:
                                self.world_select_index = (self.world_select_index - 1) % len(self.worlds_list)
                            elif self.state == "PLAYING" and self.mods_menu_open and len(self.mod_manager.available_mods) > 0:
                                self.mods_select_index = (self.mods_select_index - 1) % len(self.mod_manager.available_mods)
                        
                        elif event.key == pygame.K_DOWN and (self.state == "WORLD_SELECT" or (self.state == "PLAYING" and self.mods_menu_open)):
                            if self.state == "WORLD_SELECT" and len(self.worlds_list) > 0:
                                self.world_select_index = (self.world_select_index + 1) % len(self.worlds_list)
                            elif self.state == "PLAYING" and self.mods_menu_open and len(self.mod_manager.available_mods) > 0:
                                self.mods_select_index = (self.mods_select_index + 1) % len(self.mod_manager.available_mods)
                        
                        elif event.key == pygame.K_RETURN and self.state == "WORLD_SELECT":
                            if len(self.worlds_list) > 0 and 0 <= self.world_select_index < len(self.worlds_list):
                                world_name = self.worlds_list[self.world_select_index]['name']
                                if self.load_world(world_name):
                                    self.state = "PLAYING"
                                    try:
                                        self.play_random_music("game")
                                    except:
                                        pass
                        
                        elif event.key == pygame.K_RETURN and self.state == "WORLD_CREATE":
                            if self.world_create_name.strip():
                                self.create_new_world()
                        
                        elif event.key == pygame.K_RETURN and self.state == "PLAYING" and self.mods_menu_open:
                            if len(self.mod_manager.available_mods) > 0 and 0 <= self.mods_select_index < len(self.mod_manager.available_mods):
                                mod = self.mod_manager.available_mods[self.mods_select_index]
                                if mod['enabled']:
                                    self.mod_manager.disable_mod(mod['id'])
                                else:
                                    self.mod_manager.enable_mod(mod['id'])
                                self.mod_manager.scan_mods()
                                self.load_textures()
                        
                        elif self.state == "WORLD_CREATE" and self.typing_name:
                            if event.key == pygame.K_BACKSPACE:
                                self.world_create_name = self.world_create_name[:-1]
                            elif event.key == pygame.K_ESCAPE:
                                self.typing_name = False
                            # Символы приходят через TEXTINPUT (работает и на ПК,
                            # и с экранной клавиатуры Android), здесь только
                            # служебные клавиши - иначе буквы дублировались бы.
                    
                    if event.type == pygame.MOUSEWHEEL and self.state == "PLAYING":
                        if self.inventory_open:
                            if self.game_mode == "CREATIVE":
                                self.creative_palette_scroll = max(0, min(
                                    self.max_creative_palette_scroll,
                                    self.creative_palette_scroll - event.y
                                ))
                            else:
                                self.inventory_recipes_scroll = max(0, min(
                                    self.max_inventory_recipes_scroll,
                                    self.inventory_recipes_scroll - event.y
                                ))
                        elif self.crafting_table_open:
                            self.crafting_recipes_scroll = max(0, min(
                                self.max_crafting_recipes_scroll,
                                self.crafting_recipes_scroll - event.y
                            ))
                    
                    if event.type == pygame.MOUSEBUTTONDOWN and self.state == "PLAYING" and not self.show_death_screen:
                        current_time = time.time()
                        mx, my = event.pos
                        
                        if self.paused:
                            if self.settings_open:
                                self.handle_settings_press(mx, my)
                            elif hasattr(self, 'pause_resume_btn') and self.pause_resume_btn.collidepoint((mx, my)):
                                self.paused = False
                            elif hasattr(self, 'pause_settings_btn') and self.pause_settings_btn.collidepoint((mx, my)):
                                self.settings_open = True
                            elif hasattr(self, 'pause_exit_btn') and self.pause_exit_btn.collidepoint((mx, my)):
                                self.paused = False
                                self.save_world()
                                self.state = "WORLD_SELECT"
                                try:
                                    self.play_random_music("menu")
                                except:
                                    pass
                        elif self.mods_menu_open:
                            layout = self.get_mods_menu_layout()
                            mods_area = layout['mods_area']
                            toggle_btn = layout['toggle_btn']
                            refresh_btn = layout['refresh_btn']
                            tutorial_btn = layout['tutorial_btn']
                            close_btn = layout['close_btn']
                            
                            if toggle_btn.collidepoint((mx, my)) and len(self.mod_manager.available_mods) > 0:
                                mod = self.mod_manager.available_mods[self.mods_select_index]
                                if mod['enabled']:
                                    self.mod_manager.disable_mod(mod['id'])
                                else:
                                    self.mod_manager.enable_mod(mod['id'])
                                self.mod_manager.scan_mods()
                                self.load_textures()
                            elif refresh_btn.collidepoint((mx, my)):
                                self.mod_manager.scan_mods()
                            elif tutorial_btn.collidepoint((mx, my)):
                                tutorial_scroll = 0
                                self.draw_mods_tutorial(tutorial_scroll)
                                pygame.display.flip()
                                tutorial_wait = True
                                while tutorial_wait:
                                    for tut_event in pygame.event.get():
                                        redraw = False
                                        if tut_event.type == pygame.QUIT:
                                            tutorial_wait = False
                                            running = False
                                        elif tut_event.type == pygame.KEYDOWN:
                                            if tut_event.key == pygame.K_ESCAPE or tut_event.key == pygame.K_RETURN:
                                                tutorial_wait = False
                                            elif tut_event.key == pygame.K_DOWN:
                                                tutorial_scroll += 30
                                                redraw = True
                                            elif tut_event.key == pygame.K_UP:
                                                tutorial_scroll -= 30
                                                redraw = True
                                        elif tut_event.type == pygame.MOUSEWHEEL:
                                            tutorial_scroll -= tut_event.y * 30
                                            redraw = True
                                        elif tut_event.type == pygame.MOUSEBUTTONDOWN:
                                            if tut_event.button == 4:
                                                tutorial_scroll -= 30
                                                redraw = True
                                            elif tut_event.button == 5:
                                                tutorial_scroll += 30
                                                redraw = True
                                            elif hasattr(self, 'mods_tutorial_close_btn') and self.mods_tutorial_close_btn.collidepoint(tut_event.pos):
                                                tutorial_wait = False
                                        
                                        if redraw:
                                            tutorial_scroll = max(0, min(tutorial_scroll, getattr(self, 'mods_tutorial_max_scroll', 0)))
                                            self.draw_mods_tutorial(tutorial_scroll)
                                            pygame.display.flip()
                                continue
                            elif close_btn.collidepoint((mx, my)):
                                self.mods_menu_open = False
                            elif mods_area.collidepoint((mx, my)) and len(self.mod_manager.available_mods) > 0:
                                mods_per_page = 5
                                row_h = mods_area.height // mods_per_page
                                click_y = my - mods_area.y
                                mod_index = min(len(self.mod_manager.available_mods) - 1, max(0, self.mods_select_index - 2 + (click_y - 20) // row_h))
                                if 0 <= mod_index < len(self.mod_manager.available_mods):
                                    self.mods_select_index = mod_index
                        
                        elif self.furnace_open is not None and self.furnace_open in self.furnaces:
                            furnace = self.furnaces[self.furnace_open]
                            
                            if hasattr(self, 'furnace_close_btn') and self.furnace_close_btn.collidepoint((mx, my)):
                                self.furnace_open = None
                                self.stop_dragging()
                                continue
                            
                            if hasattr(self, 'furnace_input_rect'):
                                if self.furnace_input_rect.collidepoint((mx, my)):
                                    if event.button == 1:
                                        if self.dragging_item is None:
                                            if furnace.input_item is not None and furnace.input_count > 0:
                                                self.start_dragging(furnace.input_item, furnace.input_count, 'furnace_input', 0)
                                        else:
                                            if furnace.input_item is None or furnace.input_item == self.dragging_item:
                                                if furnace.add_input(self.dragging_item, self.dragging_count):
                                                    from_type, from_index = self.dragging_from
                                                    self._clear_slot(from_type, from_index)
                                                    self.dragging_item = None
                                    elif event.button == 3:
                                        if furnace.input_item is not None and furnace.input_count > 0 and self.dragging_item is None:
                                            half_count = furnace.input_count // 2
                                            if half_count > 0:
                                                self.start_dragging(furnace.input_item, half_count, 'furnace_input', 0)
                                                furnace.input_count -= half_count
                                                if furnace.input_count == 0:
                                                    furnace.input_item = None
                            
                            if hasattr(self, 'furnace_fuel_rect'):
                                if self.furnace_fuel_rect.collidepoint((mx, my)):
                                    if event.button == 1:
                                        if self.dragging_item is None:
                                            if furnace.fuel_item is not None and furnace.fuel_count > 0:
                                                self.start_dragging(furnace.fuel_item, furnace.fuel_count, 'furnace_fuel', 0)
                                        else:
                                            if furnace.fuel_item is None or furnace.fuel_item == self.dragging_item:
                                                if furnace.add_fuel(self.dragging_item, self.dragging_count):
                                                    from_type, from_index = self.dragging_from
                                                    self._clear_slot(from_type, from_index)
                                                    self.dragging_item = None
                                    elif event.button == 3:
                                        if furnace.fuel_item is not None and furnace.fuel_count > 0 and self.dragging_item is None:
                                            half_count = furnace.fuel_count // 2
                                            if half_count > 0:
                                                self.start_dragging(furnace.fuel_item, half_count, 'furnace_fuel', 0)
                                                furnace.fuel_count -= half_count
                                                if furnace.fuel_count == 0:
                                                    furnace.fuel_item = None
                                                    furnace.is_burning = False
                            
                            if hasattr(self, 'furnace_output_rect'):
                                if self.furnace_output_rect.collidepoint((mx, my)):
                                    if event.button == 1:
                                        if self.dragging_item is None:
                                            if furnace.output_item is not None and furnace.output_count > 0:
                                                item, count = furnace.take_output()
                                                if item is not None:
                                                    self.add_to_inventory_slot(item, count)
                            
                            if hasattr(self, 'furnace_hotbar_slot_rects'):
                                for i, slot_rect in enumerate(self.furnace_hotbar_slot_rects):
                                    if slot_rect.collidepoint((mx, my)):
                                        if event.button == 1:
                                            if self.dragging_item is None:
                                                if self.hotbar[i] is not None:
                                                    self.start_dragging(self.hotbar[i], 
                                                                      self.hotbar_counts[i], 
                                                                      'hotbar', i)
                                            else:
                                                self.stop_dragging('hotbar', i)
                                        elif event.button == 3:
                                            if self.hotbar[i] is not None and self.dragging_item is None:
                                                half_count = self.hotbar_counts[i] // 2
                                                if half_count > 0:
                                                    self.start_dragging(self.hotbar[i], 
                                                                      half_count, 
                                                                      'hotbar', i)
                                                    self.hotbar_counts[i] -= half_count
                                                    if self.hotbar_counts[i] == 0:
                                                        self.hotbar[i] = None
                                        break
                            
                            if hasattr(self, 'furnace_inventory_slot_rects'):
                                for i, slot_rect in enumerate(self.furnace_inventory_slot_rects):
                                    if slot_rect.collidepoint((mx, my)):
                                        if event.button == 1:
                                            if self.dragging_item is None:
                                                if self.inventory[i] is not None:
                                                    self.start_dragging(self.inventory[i], 
                                                                      self.inventory_counts[i], 
                                                                      'inventory', i)
                                            else:
                                                self.stop_dragging('inventory', i)
                                        elif event.button == 3:
                                            if self.inventory[i] is not None and self.dragging_item is None:
                                                half_count = self.inventory_counts[i] // 2
                                                if half_count > 0:
                                                    self.start_dragging(self.inventory[i], 
                                                                      half_count, 
                                                                      'inventory', i)
                                                    self.inventory_counts[i] -= half_count
                                                    if self.inventory_counts[i] == 0:
                                                        self.inventory[i] = None
                                        break
                        
                        elif self.inventory_open:
                            self.recipe_hover_info = None
                            
                            if self.game_mode == "CREATIVE":
                                if event.button == 4:
                                    self.creative_palette_scroll = max(0, self.creative_palette_scroll - 1)
                                    continue
                                elif event.button == 5:
                                    self.creative_palette_scroll = min(self.max_creative_palette_scroll, self.creative_palette_scroll + 1)
                                    continue
                            else:
                                if event.button == 4:
                                    self.inventory_recipes_scroll = max(0, self.inventory_recipes_scroll - 1)
                                    continue
                                elif event.button == 5:
                                    self.inventory_recipes_scroll = min(self.max_inventory_recipes_scroll, self.inventory_recipes_scroll + 1)
                                    continue
                            
                            if hasattr(self, 'close_btn_rect') and self.close_btn_rect.collidepoint((mx, my)):
                                self.inventory_open = False
                                self.stop_dragging()
                                continue
                            
                            if self.game_mode == "CREATIVE":
                                if hasattr(self, 'creative_palette_rects') and event.button == 1:
                                    for item_id, cell_rect in self.creative_palette_rects:
                                        if cell_rect.collidepoint((mx, my)):
                                            self.take_creative_item(item_id)
                                            break
                            else:
                                if hasattr(self, 'scroll_up_btn') and self.scroll_up_btn.collidepoint((mx, my)) and self.inventory_recipes_scroll > 0:
                                    self.inventory_recipes_scroll -= 1
                                    continue
                                elif hasattr(self, 'scroll_down_btn') and self.scroll_down_btn.collidepoint((mx, my)) and self.inventory_recipes_scroll < self.max_inventory_recipes_scroll:
                                    self.inventory_recipes_scroll += 1
                                    continue
                                
                                if hasattr(self, 'craft_buttons'):
                                    for key, btn_rect, recipe in self.craft_buttons:
                                        if btn_rect.collidepoint((mx, my)):
                                            if event.button == 1:
                                                self.craft_item(key, False)
                                            break
                            
                            if hasattr(self, 'hotbar_slot_rects'):
                                for i, slot_rect in enumerate(self.hotbar_slot_rects):
                                    if slot_rect.collidepoint((mx, my)):
                                        if event.button == 1:
                                            if self.dragging_item is None:
                                                if self.hotbar[i] is not None:
                                                    self.start_dragging(self.hotbar[i], 
                                                                      self.hotbar_counts[i], 
                                                                      'hotbar', i)
                                            else:
                                                self.stop_dragging('hotbar', i)
                                        elif event.button == 3:
                                            if self.hotbar[i] is not None and self.dragging_item is None:
                                                half_count = self.hotbar_counts[i] // 2
                                                if half_count > 0:
                                                    self.start_dragging(self.hotbar[i], 
                                                                      half_count, 
                                                                      'hotbar', i)
                                                    self.hotbar_counts[i] -= half_count
                                                    if self.hotbar_counts[i] == 0:
                                                        self.hotbar[i] = None
                                        break
                            
                            if hasattr(self, 'inventory_slot_rects'):
                                for i, slot_rect in enumerate(self.inventory_slot_rects):
                                    if slot_rect.collidepoint((mx, my)):
                                        if event.button == 1:
                                            if self.dragging_item is None:
                                                if self.inventory[i] is not None:
                                                    self.start_dragging(self.inventory[i], 
                                                                      self.inventory_counts[i], 
                                                                      'inventory', i)
                                            else:
                                                self.stop_dragging('inventory', i)
                                        elif event.button == 3:
                                            if self.inventory[i] is not None and self.dragging_item is None:
                                                half_count = self.inventory_counts[i] // 2
                                                if half_count > 0:
                                                    self.start_dragging(self.inventory[i], 
                                                                      half_count, 
                                                                      'inventory', i)
                                                    self.inventory_counts[i] -= half_count
                                                    if self.inventory_counts[i] == 0:
                                                        self.inventory[i] = None
                                        break
                        
                        elif self.crafting_table_open:
                            self.recipe_hover_info = None
                            
                            if event.button == 4:
                                self.crafting_recipes_scroll = max(0, self.crafting_recipes_scroll - 1)
                                continue
                            elif event.button == 5:
                                self.crafting_recipes_scroll = min(self.max_crafting_recipes_scroll, self.crafting_recipes_scroll + 1)
                                continue
                            
                            if hasattr(self, 'crafting_close_btn') and self.crafting_close_btn.collidepoint((mx, my)):
                                self.crafting_table_open = False
                                self.stop_dragging()
                                continue
                            
                            if hasattr(self, 'craft_scroll_up_btn') and self.craft_scroll_up_btn.collidepoint((mx, my)) and self.crafting_recipes_scroll > 0:
                                self.crafting_recipes_scroll -= 1
                                continue
                            elif hasattr(self, 'craft_scroll_down_btn') and self.craft_scroll_down_btn.collidepoint((mx, my)) and self.crafting_recipes_scroll < self.max_crafting_recipes_scroll:
                                self.crafting_recipes_scroll += 1
                                continue
                            
                            elif hasattr(self, 'crafting_table_buttons'):
                                for key, btn_rect, recipe in self.crafting_table_buttons:
                                    if btn_rect.collidepoint((mx, my)):
                                        if event.button == 1:
                                            self.craft_item(key, True)
                                        break
                        
                        elif self.state == "PLAYING" and not self.mods_menu_open:
                            # На touch-устройствах SDL дублирует тапы как
                            # синтетические клики мыши - если палец попал в
                            # зону джойстика/кнопок, не даём этому клику ещё
                            # и провзаимодействовать с миром позади них.
                            if self.touch_device_detected:
                                mx, my = event.pos
                                if self.mobile_ui_hit((mx, my)):
                                    continue
                            
                            effective_button = event.button
                            if self.touch_device_detected and event.button == 1 and self.mobile_action_mode == 'place':
                                effective_button = 3
                            
                            if effective_button == 4:
                                self.selected_slot = (self.selected_slot - 1) % self.hotbar_slots
                            elif effective_button == 5:
                                self.selected_slot = (self.selected_slot + 1) % self.hotbar_slots
                            elif effective_button == 1:
                                mx, my = event.pos
                                gx = int((mx + self.camera_x) // 40)
                                gy = int((my + self.camera_y) // 40)
                                _mo = self.get_multitile_origin(gx, gy)
                                if _mo is not None:
                                    gx, gy = _mo
                                
                                if (gx, gy) in self.world:
                                    block_id = self.world[(gx, gy)][0]
                                    if block_id in [CRAFTING_TABLE, FURNACE, WOODEN_DOOR, PINE_DOOR, TORCH]:
                                        self.start_mining(gx, gy)
                                    else:
                                        self.start_mining(gx, gy)
                                
                            elif effective_button == 3:
                                mx, my = event.pos
                                gx = int((mx + self.camera_x) // 40)
                                gy = int((my + self.camera_y) // 40)
                                _mo = self.get_multitile_origin(gx, gy)
                                if _mo is not None:
                                    gx, gy = _mo
                                
                                if 0 <= gy < self.world_h:
                                    if (gx, gy) in self.world:
                                        block_id = self.world[(gx, gy)][0]
                                        
                                        if block_id in [WOODEN_DOOR, PINE_DOOR]:
                                            self.toggle_door(gx, gy)
                                            continue
                                        
                                        if block_id == CRAFTING_TABLE:
                                            if current_time - self.last_click_time > self.click_cooldown:
                                                self.crafting_table_open = True
                                                self.inventory_open = False
                                                self.furnace_open = None
                                                self.mods_menu_open = False
                                                self.last_click_time = current_time
                                            continue
                                        
                                        if block_id == FURNACE:
                                            if current_time - self.last_click_time > self.click_cooldown:
                                                if (gx, gy) not in self.furnaces:
                                                    self.furnaces[(gx, gy)] = Furnace(gx, gy)
                                                self.furnace_open = (gx, gy)
                                                self.inventory_open = False
                                                self.crafting_table_open = False
                                                self.mods_menu_open = False
                                                self.last_click_time = current_time
                                            continue
                                    
                                    selected_item = self.get_selected_item()
                                    if selected_item is not None and not self.show_death_screen:
                                        if selected_item in self.placeable_blocks:
                                            if self.can_place_block(gx, gy, selected_item):
                                                if self.get_selected_item_count() > 0:
                                                    if selected_item in [WOODEN_DOOR, PINE_DOOR]:
                                                        if self.place_door(gx, gy, selected_item):
                                                            self.remove_from_inventory_slot(selected_item, 1)
                                                    elif selected_item == FURNACE:
                                                        self.world[(gx, gy)] = [FURNACE, 0, False]
                                                        self.furnaces[(gx, gy)] = Furnace(gx, gy)
                                                        self.remove_from_inventory_slot(selected_item, 1)
                                                    elif selected_item == TORCH:
                                                        if self.place_torch(gx, gy):
                                                            self.remove_from_inventory_slot(selected_item, 1)
                                                    else:
                                                        was_liquid = self.world.get((gx, gy), [EMPTY])[0] in (WATER, LAVA)
                                                        self.world[(gx, gy)] = [
                                                            selected_item, 
                                                            MAX_LIQUID_LEVEL if selected_item in [WATER, LAVA] else 0, 
                                                            False
                                                        ]
                                                        if selected_item in (SAND, ASH, WATER, LAVA):
                                                            self.active_physics_tiles.add((gx, gy))
                                                        self.remove_from_inventory_slot(selected_item, 1)
                                                        if was_liquid and selected_item not in (WATER, LAVA):
                                                            self.dry_up_disconnected_liquid(gx, gy)
                    
                    elif event.type == pygame.MOUSEBUTTONDOWN and self.state != "PLAYING":
                        mx, my = event.pos
                        
                        if self.state == "MAIN_MENU":
                            center_x = WIDTH // 2
                            btn_width, btn_height = 300, 60
                            btn_y_start = 280
                            
                            single_btn = pygame.Rect(center_x - btn_width // 2, btn_y_start, btn_width, btn_height)
                            mods_btn = pygame.Rect(center_x - btn_width // 2, btn_y_start + 160, btn_width, btn_height)
                            quit_btn = pygame.Rect(center_x - btn_width // 2, btn_y_start + 240, btn_width, btn_height)
                            
                            if single_btn.collidepoint((mx, my)):
                                self.state = "WORLD_SELECT"
                                self.refresh_worlds_list()
                            elif mods_btn.collidepoint((mx, my)):
                                self.mod_manager.scan_mods()
                                self.draw_mods_menu()
                                pygame.display.flip()
                                mods_wait = True
                                while mods_wait:
                                    for mod_event in pygame.event.get():
                                        if mod_event.type == pygame.QUIT:
                                            mods_wait = False
                                            running = False
                                        elif mod_event.type == pygame.KEYDOWN:
                                            if mod_event.key == pygame.K_ESCAPE:
                                                mods_wait = False
                                        elif mod_event.type == pygame.MOUSEBUTTONDOWN:
                                            mod_mx, mod_my = mod_event.pos
                                            layout = self.get_mods_menu_layout()
                                            mods_area = layout['mods_area']
                                            close_btn = layout['close_btn']
                                            if close_btn.collidepoint((mod_mx, mod_my)):
                                                mods_wait = False
                                            elif mods_area.collidepoint((mod_mx, mod_my)) and len(self.mod_manager.available_mods) > 0:
                                                mods_per_page = 5
                                                row_h = mods_area.height // mods_per_page
                                                click_y = mod_my - mods_area.y
                                                mod_index = min(len(self.mod_manager.available_mods) - 1, max(0, self.mods_select_index - 2 + (click_y - 20) // row_h))
                                                if 0 <= mod_index < len(self.mod_manager.available_mods):
                                                    self.mods_select_index = mod_index
                                                    self.draw_mods_menu()
                                                    pygame.display.flip()
                            elif quit_btn.collidepoint((mx, my)):
                                running = False
                        
                        elif self.state == "WORLD_SELECT":
                            center_x = WIDTH // 2
                            btn_y = 150 + 400 + 30
                            
                            create_btn = pygame.Rect(center_x - 280, btn_y, 180, 50)
                            delete_btn = pygame.Rect(center_x - 80, btn_y, 180, 50)
                            mods_btn = pygame.Rect(center_x + 120, btn_y, 160, 50)
                            back_btn = pygame.Rect(center_x + 300, btn_y, 160, 50)
                            
                            if create_btn.collidepoint((mx, my)):
                                self.state = "WORLD_CREATE"
                                self.world_create_name = ""
                                self.world_create_mode = "SURVIVAL"
                                self.typing_name = True
                            elif delete_btn.collidepoint((mx, my)) and len(self.worlds_list) > 0:
                                world_name = self.worlds_list[self.world_select_index]['name']
                                self.delete_world(world_name)
                                if self.world_select_index >= len(self.worlds_list):
                                    self.world_select_index = max(0, len(self.worlds_list) - 1)
                            elif mods_btn.collidepoint((mx, my)):
                                self.mod_manager.scan_mods()
                                self.draw_mods_menu()
                                pygame.display.flip()
                                mods_wait = True
                                while mods_wait:
                                    for mod_event in pygame.event.get():
                                        if mod_event.type == pygame.QUIT:
                                            mods_wait = False
                                            running = False
                                        elif mod_event.type == pygame.KEYDOWN:
                                            if mod_event.key == pygame.K_ESCAPE:
                                                mods_wait = False
                                        elif mod_event.type == pygame.MOUSEBUTTONDOWN:
                                            mod_mx, mod_my = mod_event.pos
                                            layout = self.get_mods_menu_layout()
                                            close_btn = layout['close_btn']
                                            if close_btn.collidepoint((mod_mx, mod_my)):
                                                mods_wait = False
                            elif back_btn.collidepoint((mx, my)):
                                self.state = "MAIN_MENU"
                            
                            worlds_per_page = 5
                            start_index = max(0, self.world_select_index - 2)
                            world_area = pygame.Rect(center_x - 300, 150, 600, 400)
                            
                            if world_area.collidepoint((mx, my)):
                                click_y = my - 150
                                world_index = start_index + (click_y - 30) // 70
                                if 0 <= world_index < len(self.worlds_list):
                                    self.world_select_index = world_index
                                    if event.button == 1:
                                        world_name = self.worlds_list[world_index]['name']
                                        if self.load_world(world_name):
                                            self.state = "PLAYING"
                                            try:
                                                self.play_random_music("game")
                                            except:
                                                pass
                        
                        elif self.state == "WORLD_CREATE":
                            center_x = WIDTH // 2
                            create_area = pygame.Rect(center_x - 300, 150, 600, 380)
                            btn_y = create_area.bottom + 30
                            
                            name_input = pygame.Rect(create_area.x + 50, create_area.y + 60, 500, 50)
                            limited_btn = pygame.Rect(create_area.x + 50, create_area.y + 164, 240, 50)
                            infinite_btn = pygame.Rect(create_area.x + 310, create_area.y + 164, 240, 50)
                            survival_btn = pygame.Rect(create_area.x + 50, create_area.y + 268, 240, 50)
                            creative_btn = pygame.Rect(create_area.x + 310, create_area.y + 268, 240, 50)
                            create_btn = pygame.Rect(center_x - 140, btn_y, 130, 50)
                            cancel_btn = pygame.Rect(center_x + 20, btn_y, 130, 50)
                            
                            if name_input.collidepoint((mx, my)):
                                self.typing_name = True
                            elif limited_btn.collidepoint((mx, my)):
                                self.world_type = "LIMITED"
                                self.typing_name = False
                            elif infinite_btn.collidepoint((mx, my)):
                                self.world_type = "INFINITE"
                                self.typing_name = False
                            elif survival_btn.collidepoint((mx, my)):
                                self.world_create_mode = "SURVIVAL"
                                self.typing_name = False
                            elif creative_btn.collidepoint((mx, my)):
                                self.world_create_mode = "CREATIVE"
                                self.typing_name = False
                            elif create_btn.collidepoint((mx, my)):
                                if self.world_create_name.strip():
                                    self.create_new_world()
                            elif cancel_btn.collidepoint((mx, my)):
                                self.state = "WORLD_SELECT"
                                self.typing_name = False
                            else:
                                self.typing_name = False
                    
                    if event.type == pygame.MOUSEBUTTONUP and self.state == "PLAYING":
                        if event.button == 1:
                            self.stop_mining()
                        if self.dragging_slider:
                            self.dragging_slider = None
                            self.save_settings()
                    
                    if event.type == pygame.MOUSEMOTION and self.state == "PLAYING":
                        if self.paused and self.settings_open and self.dragging_slider:
                            self.handle_settings_drag(event.pos[0])
                        elif self.inventory_open or self.crafting_table_open:
                            mx, my = event.pos
                            self.recipe_hover_info = None
                            
                            if self.inventory_open and hasattr(self, 'craft_buttons'):
                                for key, btn_rect, recipe in self.craft_buttons:
                                    if btn_rect.collidepoint((mx, my)):
                                        self.recipe_hover_info = recipe
                                        break
                            elif self.crafting_table_open and hasattr(self, 'crafting_table_buttons'):
                                for key, btn_rect, recipe in self.crafting_table_buttons:
                                    if btn_rect.collidepoint((mx, my)):
                                        self.recipe_hover_info = recipe
                                        break
                
                if self.state == "PLAYING":
                    self.update_lighting()
                    self.update_dropped_items()
                    self.update_furnaces()
                    
                    if not self.paused:
                        self.update_mining()
                        self.update_player()
                        self.update_physics()
                        self.update_infinite_world()
                        self.update_ash_particles()
                
                self.draw()
                pygame.display.flip()
                self.clock.tick(FPS)
            except Exception as e:
                print(f"Ошибка в главном цикле: {e}")
                # Продолжаем выполнение, не вылетаем
    
    def create_new_world(self):
        if not self.world_create_name.strip():
            return
        
        self.current_world_name = self.world_create_name.strip()
        self.game_mode = self.world_create_mode
        self.creative_flying = False
        
        self.world = {}
        self.generated_terrain = set()
        self.generated_decor = set()
        self.generated_ores = set()
        
        self.seed = random.randint(0, 100000)
        self.biome_offset = random.randint(0, 5000)
        
        self.health = 20
        self.max_health = 20
        self.timer = 0
        self.show_death_screen = False
        
        self.day_time_ticks = 120 * FPS
        self.is_night = False
        self.day_night_cycle = True
        
        self.furnaces = {}
        self.torches = {}
        self.dropped_items = []
        self.door_states = {}
        
        self.hotbar = [None] * self.hotbar_slots
        self.inventory = [None] * self.inventory_slots
        self.hotbar_counts = [0] * self.hotbar_slots
        self.inventory_counts = [0] * self.inventory_slots
        
        self.selected_slot = 0
        self.player_facing = "right"
        
        self.inventory_recipes_scroll = 0
        self.crafting_recipes_scroll = 0
        
        self.player_rect = pygame.Rect(WIDTH//2, 100, 24, 64)
        self.vel_y = 0
        self.on_ground = False
        self.camera_x = 0
        self.camera_y = 0
        self.is_swimming = False
        self.fall_distance = 0
        self.last_ground_y = self.player_rect.bottom
        
        self.inventory_open = False
        self.crafting_table_open = False
        self.furnace_open = None
        self.mods_menu_open = False
        self.paused = False
        self.settings_open = False
        
        px = int(self.player_rect.centerx // TILE_SIZE)
        for x in range(px - UPDATE_DISTANCE, px + UPDATE_DISTANCE):
            self.generate_chunk(x)
        for x in range(px - RENDER_DISTANCE, px + RENDER_DISTANCE):
            self.plant_decor(x)
        
        self.state = "PLAYING"
        try:
            self.play_random_music("game")
        except:
            pass
        
        print(f"Создан новый мир: {self.current_world_name}")

if __name__ == "__main__":
    try:
        game = Game()
        game.run()
    except Exception as e:
        print(f"Критическая ошибка: {e}")
        import traceback
        traceback.print_exc()
    finally:
        pygame.quit()
        sys.exit()
