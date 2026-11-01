# Driver Monitoring System (DMS) with ESP32-CAM

Prototype de détection de somnolence du conducteur utilisant une **ESP32-CAM** et la vision par ordinateur.

## Présentation

L'ESP32-CAM capture des images du visage et les transmet par Wi-Fi à un programme Python. **MediaPipe** détecte les points caractéristiques des yeux et **OpenCV** permet de visualiser le résultat. Le programme calcule l'**EAR (Eye Aspect Ratio)** pour repérer une fermeture prolongée des yeux et envoyer une commande d'alerte à l'ESP32-CAM.

## Fonctionnalités

- Capture d'images avec l'ESP32-CAM via Wi-Fi
- Détection du visage et suivi des yeux
- Calcul de l'EAR et calibration du seuil
- Détection d'une fermeture prolongée des yeux (durée configurable)
- Commande d'une LED rouge et d'un buzzer selon le matériel utilisé
- Affichage de l'état du conducteur et enregistrement vidéo

## Matériel

- ESP32-CAM (AI Thinker) et adaptateur USB ESP32-CAM-MB
- Breadboard et fils Dupont
- LED rouge et résistance de 220 à 330 Ω
- Buzzer actif 3,3 V adapté au courant disponible, ou buzzer avec circuit de commande approprié
- PC pour exécuter l'analyse Python

## Technologies

**Python**, **OpenCV**, **MediaPipe**, **NumPy**, **Requests**, **C++ / Arduino IDE**, **Wi-Fi / HTTP**.

## Architecture

```text
ESP32-CAM -- images JPEG via Wi-Fi --> PC (Python + MediaPipe + OpenCV)
ESP32-CAM <-- commandes HTTP -------- PC (détection EAR)
     |
     +-- GPIO 13 --> résistance --> LED rouge
     +-- GPIO 14 --> commande buzzer (selon le type)
```

## Câblage de principe

| ESP32-CAM | Connexion |
| --- | --- |
| GPIO 13 | Résistance 220–330 Ω puis anode de la LED |
| GND | Cathode de la LED |
| GPIO 14 | Entrée de commande du buzzer / circuit de pilotage |
| GND | Masse commune |

> **Attention :** les broches peuvent être masquées quand l'ESP32-CAM est enfichée dans l'adaptateur MB. Ne supposez pas que les contacts 5 V/GND de l'adaptateur sont accessibles sans vérification. Ne branchez pas un buzzer 5 V ou à forte consommation directement sur un GPIO. GPIO 13 et 14 peuvent aussi être utilisés par la carte microSD.

## Installation

1. Ouvrir le programme `.ino` dans **Arduino IDE** et sélectionner la carte **AI Thinker ESP32-CAM**.
2. Configurer le nom et le mot de passe Wi-Fi, puis téléverser le programme.
3. Relever l'adresse IP de l'ESP32-CAM dans le moniteur série.
4. Installer les dépendances Python :

   ```powershell
   py -3.13 -m pip install mediapipe==0.10.35 opencv-python numpy requests
   ```

5. Renseigner l'adresse IP de l'ESP32-CAM dans `dms.py` :

   ```python
   ESP32_IP = "192.168.x.x"
   ```

6. Démarrer le programme :

   ```powershell
   py -3.13 dms.py
   ```

> Le script Python pour MediaPipe 0.10.35 doit utiliser l'API **Face Landmarker** (et non `mp.solutions.face_mesh`). Selon l'implémentation, le modèle `face_landmarker.task` doit être téléchargé au premier lancement ou placé à côté du script.

## Utilisation

Dans la fenêtre vidéo du programme Python :

| Touche | Action |
| --- | --- |
| `C` | Calibration avec les yeux ouverts |
| `X` | Calibration avec les yeux fermés |
| `Q` | Quitter et terminer l'enregistrement |

Après calibration, une fermeture prolongée des yeux entraîne une commande d'alerte. La durée de détection et les seuils sont configurables dans le script.

## API HTTP de l'ESP32-CAM

| Route | Fonction |
| --- | --- |
| `/capture` | Récupérer une image JPEG |
| `/alert` | Activer l'alerte |
| `/safe` | Désactiver l'alerte |

La disponibilité d'autres routes (par exemple `/stop`) dépend du sketch Arduino utilisé.

## Limites

La précision dépend de l'éclairage, de l'orientation du visage, de la fréquence des images et de la calibration. La commande du buzzer doit être testée avec le composant réel. Ce projet est un **prototype pédagogique**, et non un système de sécurité automobile certifié.

## Contexte

Projet réalisé dans le cadre du module **Sécurité des systèmes embarqués**.
