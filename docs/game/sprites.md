# Escritório ao vivo — guia de sprites

Lista de todas as imagens que o painel animado precisa, com o prompt de cada uma para gerar no ChatGPT.

## Como funciona a animação (por que são poucas imagens)

A parte "viva" vem do código, não de centenas de quadros:

- **Poses-chave geradas pela IA** (parado, andando, digitando, dormindo…).
- **Movimento por código:** respiração, balanço ao andar, pulo de comemoração, squash & stretch, partículas, brilho das máquinas, luz do monitor, moedas voando, transição dia/noite.
- **Espelhamento:** cada personagem é gerado olhando para um lado só; o código espelha para o outro. Com frente 3/4 e costas 3/4 espelhadas, temos as 4 direções da vista isométrica.
- **Interface por código:** balões de fala, nomes, barras de limite e números são desenhados pelo código (texto nítido e nos 3 idiomas). As imagens **nunca** devem ter texto.

## Ambientes personalizáveis (pensado desde já)

Os arquivos ficam separados em duas partes:

- `shared/` — personagens, robozinho, gato, máquinas das ferramentas, efeitos e ícones. Servem para **qualquer** ambiente.
- `themes/<nome>/` — fundo e móveis de cada ambiente.

Para criar um ambiente novo no futuro (startup, home office, café, estação espacial…), basta gerar só a seção **3. Ambiente** de novo, com outra descrição. Começamos pelo tema `loft`: um estúdio/escritório descolado.

## Fluxo no ChatGPT (para manter tudo consistente)

1. **Gere primeiro a arte-chave (3.1).** Ela define o estilo. Refaça até gostar.
2. Em toda imagem seguinte, **anexe a arte-chave** e cole o **bloco de estilo** abaixo antes do prompt.
3. Para cada personagem, gere primeiro a **ficha de referência** (2.x.0). Nas poses dele, **anexe essa ficha** e diga "same character as the attached reference".
4. Prefira fazer tudo **na mesma conversa** do ChatGPT; ele mantém melhor o estilo.
5. Peça sempre em PNG com **fundo transparente**. Se não sair transparente, peça "solid flat magenta #FF00FF background" que eu removo.
6. Nas tiras de animação (2, 3 ou 4 quadros), **não precisa de grade perfeita**: eu recorto cada quadro automaticamente e alinho os pés. Só precisa ter espaço entre os quadros.
7. Salve com o **nome de arquivo indicado** em `assets-src/` (eu crio a pasta). Eu processo, redimensiono e monto as folhas.

**Comece pequeno:** para o protótipo bastam a arte-chave, o fundo, os móveis, **2 personagens**, 2 máquinas (RTK e Graphify) e os ícones. O resto entra depois.

---

## Bloco de estilo (cole antes de todo prompt)

```
STYLE: polished 2D game art for a cozy, modern office management game. Isometric 3/4 top-down view (2:1 isometric angle), camera looking down from the front-right, soft light coming from the upper left. Clean cel shading with soft gradients and gentle ambient occlusion, crisp outlines in a darker shade of each color (never pure black), smooth anti-aliased edges, NOT pixel art, NOT 3D render, NOT photorealistic. Stylized proportions: heads slightly large (about 1:4 head-to-body), friendly but not childish, not chibi. Palette: warm wood, cream and warm-gray walls, deep teal and coral accents, soft purple and amber for lights. No text, no letters, no numbers, no logos, no watermark.
```

Para personagens e objetos soltos, acrescente:

```
Single isolated asset, full body / full object visible, centered, transparent background PNG, no floor, no shadow on the ground (I add shadows in code), consistent scale.
```

---

## 1. Lista resumida

| # | Arquivo(s) | Quantidade | Prioridade |
|---|---|---|---|
| 3.1 | `loft_keyart.png` | 1 | protótipo |
| 3.2 | `loft_bg_day.png`, `loft_bg_night.png` | 2 | protótipo |
| 3.3 | móveis do loft | 14 | protótipo |
| 2.1–2.2 | personagens Nina e Theo | 2 × 10 | protótipo |
| 2.3–2.6 | personagens Kai, Lia, Bruno, Maya | 4 × 10 | depois |
| 4 | robozinho (subagente) | 3 | protótipo |
| 5 | gato do escritório | 4 | depois |
| 6 | máquinas das ferramentas | 6 × 2 | RTK e mapa no protótipo |
| 7 | fichas e efeitos | 4 | protótipo |
| 8 | ícones dos balões | 1 folha | protótipo |

---

## 2. Personagens (os agentes)

Cada sessão ativa vira um personagem. Seis tipos variados, sem relação com marca. A cor da equipe (laranja para Claude Code, azul-petróleo para Codex) aparece num crachá flutuante desenhado pelo código, então qualquer personagem serve para qualquer agente.

Cada personagem tem 10 imagens:

| Arquivo | O que é | Quadros |
|---|---|---|
| `<nome>_ref.png` | ficha de referência (não entra no jogo) | — |
| `<nome>_idle.png` | parado, de frente | 1 |
| `<nome>_walk_front.png` | andando em direção à câmera | 4 |
| `<nome>_walk_back.png` | andando de costas | 4 |
| `<nome>_type.png` | sentado digitando | 2 |
| `<nome>_think.png` | sentado pensando | 1 |
| `<nome>_sleep.png` | cochilando na mesa | 1 |
| `<nome>_machine.png` | de costas, operando um painel | 2 |
| `<nome>_celebrate.png` | comemorando | 1 |
| `<nome>_coffee.png` | em pé tomando café (esperando) | 1 |

### Descrições dos personagens

Use a descrição do personagem no lugar de `<CHARACTER>` nos prompts de pose.

- **2.1 Nina** (`nina`): `a young woman with dark brown skin and voluminous curly black hair tied in a high puff, oversized mustard-yellow knit sweater, dark green cargo pants, white chunky sneakers, over-ear headphones resting around her neck`
- **2.2 Theo** (`theo`): `a man in his thirties with short ginger hair and a trimmed beard, round thin-frame glasses, open red-and-navy flannel overshirt over a plain cream t-shirt with rolled sleeves, dark jeans, brown boots`
- **2.3 Kai** (`kai`): `a young East Asian person with a black undercut hairstyle, teal oversized hoodie with the hood down, black joggers, white sneakers with teal details, a small silver earring`
- **2.4 Lia** (`lia`): `a woman in her fifties with a silver bob haircut, round tortoiseshell glasses, light denim jacket over a coral striped top, beige trousers, comfortable loafers`
- **2.5 Bruno** (`bruno`): `a tall Black man with long locs tied up in a bun, coral crewneck sweatshirt, olive cargo pants, gray high-top sneakers, a smartwatch`
- **2.6 Maya** (`maya`): `a woman in her late twenties with long wavy chestnut-brown hair in a loose low ponytail, small gold stud earrings, soft lavender knit cardigan over a white t-shirt, straight dark-blue jeans, white sneakers, a small backpack strap on one shoulder`

### Prompts de pose

**`<nome>_ref.png` — ficha de referência**
```
Character reference sheet of <CHARACTER>. Two full-body views side by side with clear space between them: (1) standing relaxed, three-quarter view facing down-right toward the camera; (2) standing, three-quarter view from behind facing up-left away from the camera. Same character, same outfit, same proportions in both. Neutral friendly expression. Transparent background.
```

**`<nome>_idle.png`**
```
Same character as the attached reference: <CHARACTER>. Full body, standing relaxed, weight slightly on one leg, arms loose, a small friendly smile. Three-quarter view facing down-right toward the camera, isometric perspective. Transparent background.
```

**`<nome>_walk_front.png`**
```
Same character as the attached reference: <CHARACTER>. Horizontal sprite strip of 4 frames of a walk cycle, evenly spaced with clear empty space between frames, same size and same ground line in every frame. Three-quarter view walking down-right toward the camera, isometric perspective. Frames: 1 contact (left foot forward), 2 passing, 3 contact (right foot forward), 4 passing. Natural arm swing, relaxed confident walk. Transparent background.
```

**`<nome>_walk_back.png`**
```
Same character as the attached reference: <CHARACTER>. Horizontal sprite strip of 4 frames of a walk cycle, evenly spaced with clear empty space between frames, same size and same ground line in every frame. Three-quarter view from behind, walking up-left away from the camera, isometric perspective. Frames: 1 contact (left foot forward), 2 passing, 3 contact (right foot forward), 4 passing. Natural arm swing. Transparent background.
```

**`<nome>_type.png`**
```
Same character as the attached reference: <CHARACTER>. Horizontal sprite strip of 2 frames, clear space between them, same size and position. The character is seated (no chair and no desk drawn, just the seated body as if on an office chair), three-quarter view facing down-right toward the camera, both forearms forward at desk height typing on an invisible keyboard, focused expression. Frame 1: hands slightly raised. Frame 2: hands pressing down, head tilted slightly. Transparent background.
```

**`<nome>_think.png`**
```
Same character as the attached reference: <CHARACTER>. Seated (no chair or desk drawn), three-quarter view facing down-right toward the camera, leaning back a little, one hand on the chin, eyes looking up thoughtfully. Transparent background.
```

**`<nome>_sleep.png`**
```
Same character as the attached reference: <CHARACTER>. Seated (no chair or desk drawn), three-quarter view facing down-right, arms folded forward at desk height with the head resting on the arms, eyes closed, peaceful nap. Transparent background.
```

**`<nome>_machine.png`**
```
Same character as the attached reference: <CHARACTER>. Horizontal sprite strip of 2 frames, clear space between them, same size and position. Standing, three-quarter view from behind facing up-left, both hands raised to chest height operating a control panel in front of them (the panel itself is not drawn). Frame 1: right hand pressing forward. Frame 2: left hand pressing forward, head tilted. Transparent background.
```

**`<nome>_celebrate.png`**
```
Same character as the attached reference: <CHARACTER>. Full body, three-quarter view facing down-right toward the camera, jumping slightly with both fists raised in celebration, big happy smile, feet just above the ground. Transparent background.
```

**`<nome>_coffee.png`**
```
Same character as the attached reference: <CHARACTER>. Full body standing, three-quarter view facing down-right toward the camera, holding a ceramic coffee mug with both hands near the chest, relaxed waiting pose, calm half-smile. Transparent background.
```

---

## 3. Ambiente `loft` (tema 1)

### 3.1 `loft_keyart.png` — arte-chave (faça primeiro)
Esta imagem não entra no jogo. Ela fixa o estilo de tudo.
```
Key art of a cool modern tech loft office seen in isometric 3/4 top-down view, one room shown as a cutaway with two walls (back-left and back-right) and no front walls. Exposed brick on one wall, warm-white plaster on the other, large industrial steel-frame window with a city skyline, warm wood floor with a big soft rug, hanging pendant lamps, lots of plants, a lounge corner with a sofa, a coffee station, bookshelves, four desks with monitors in an open layout, and a few futuristic but friendly machines along the walls with softly glowing panels. Three diverse people working casually. Cozy, vibrant, inviting atmosphere, late afternoon light. Polished 2D game art, clean cel shading with soft gradients, not pixel art, not 3D render. No text, no logos. 16:9.
```

### 3.2 Fundo vazio (dia e noite)
`loft_bg_day.png` — gere com a arte-chave anexada:
```
Same style and same room as the attached key art, but EMPTY: only the floor, the two walls, the big industrial window with the city skyline, pendant lamps hanging from above, baseboards and wall details. No furniture, no desks, no machines, no plants, no people. Large open floor area to place furniture later. Daytime, warm sunlight entering through the window and casting soft light shapes on the floor. Isometric 3/4 top-down cutaway, 16:9, no text.
```
`loft_bg_night.png` — **edite a imagem do dia** (anexe `loft_bg_day.png`):
```
Same exact image, same composition and every element in the same position, but at night: dark blue sky with city lights in the window, the pendant lamps turned on casting warm pools of light, a subtle purple ambient glow. Do not move or add anything.
```

### 3.3 Móveis e objetos
Use o bloco de estilo + "Single isolated asset…" e a arte-chave anexada. Todos na mesma vista isométrica.

| Arquivo | Prompt (depois do estilo) |
|---|---|
| `loft_desk.png` | `A modern wooden office desk seen from the front in isometric view, with a slim widescreen monitor (screen facing away from the camera, we see its back), a keyboard, a small plant and a mug. The front side of the desk faces the camera. Transparent background.` |
| `loft_desk_b.png` | `Variation of a modern office desk in isometric view: white top with light wood legs, dual monitors facing away from the camera, a desk lamp and a stack of notebooks. Transparent background.` |
| `loft_chair.png` | `An ergonomic office chair in isometric view, seat facing the camera (down-right), charcoal fabric with teal accents, empty. Transparent background.` |
| `loft_sofa.png` | `A cozy mid-century three-seat sofa in terracotta fabric with two cushions, isometric view, facing down-right. Transparent background.` |
| `loft_coffee.png` | `A coffee station: a small wooden counter with a shiny espresso machine, a grinder, mugs on hooks and a small plant, isometric view, against-the-wall piece. Transparent background.` |
| `loft_bookshelf.png` | `A tall wooden bookshelf full of colorful books without readable titles, small figurines and plants, isometric view, against-the-wall piece. Transparent background.` |
| `loft_plant_tall.png` | `A tall monstera plant in a ceramic pot, isometric view. Transparent background.` |
| `loft_plant_small.png` | `A small succulent arrangement in a round concrete pot, isometric view. Transparent background.` |
| `loft_rug.png` | `A large soft rectangular rug with a subtle geometric pattern in teal, cream and coral, lying flat on the floor, seen in isometric perspective as a diamond shape. Transparent background.` |
| `loft_whiteboard.png` | `A whiteboard on a rolling stand with colorful sticky notes and abstract doodles (no readable text), isometric view. Transparent background.` |
| `loft_door_closed.png` | `An office door in a back wall, wood with a frosted glass panel, closed, isometric view matching a back-right wall. Transparent background.` |
| `loft_door_open.png` | `The same office door as the attached image but open, swung inward, with a soft light coming from the doorway. Same size and angle. Transparent background.` |
| `loft_alarm_off.png` | `A small round industrial warning lamp mounted on a wall bracket, glass dome, light turned off, isometric view. Transparent background.` |
| `loft_alarm_on.png` | `The same warning lamp as the attached image, now glowing bright red with a soft halo. Same size and angle. Transparent background.` |

---

## 4. Robozinho ajudante (subagentes)
Quando um agente chama um subagente, nasce um robozinho que trabalha e some ao terminar. Arquivos em `shared/`.

| Arquivo | Prompt (depois do estilo) |
|---|---|
| `bot_ref.png` | `Character design of a small friendly helper robot that floats in the air: rounded capsule body in off-white with teal panels, a dark glass face screen with two simple glowing eyes, tiny hover thruster below, two small rounded arms. Cute but sleek, not childish. Two views side by side: three-quarter front facing down-right, and three-quarter back facing up-left. Transparent background.` |
| `bot_float.png` | `Same robot as the attached reference. Horizontal sprite strip of 2 frames, clear space between them: hovering idle, three-quarter view facing down-right. Frame 1 eyes open, frame 2 eyes in a happy blink, thruster glow slightly different. Transparent background.` |
| `bot_work.png` | `Same robot as the attached reference. Horizontal sprite strip of 2 frames, clear space between them: hovering and working with both little arms extended forward, eyes as focused lines, three-quarter view facing down-right. Small difference between frames in arm position. Transparent background.` |

---

## 5. Gato do escritório (charme extra, depois)
Passeia, senta e dorme no sofá. Arquivos em `shared/`.

| Arquivo | Prompt (depois do estilo) |
|---|---|
| `cat_walk.png` | `A chubby gray tabby office cat with a teal collar. Horizontal sprite strip of 4 frames of a walk cycle, clear space between frames, same size and ground line, three-quarter view walking down-right. Transparent background.` |
| `cat_sit.png` | `The same gray tabby cat with a teal collar sitting upright, tail curled around the paws, three-quarter view facing down-right. Transparent background.` |
| `cat_sleep.png` | `The same gray tabby cat curled up asleep in a ball, three-quarter view. Transparent background.` |
| `cat_stretch.png` | `The same gray tabby cat doing a big stretch, front legs forward and back raised, three-quarter view facing down-right. Transparent background.` |

---

## 6. Máquinas das ferramentas de economia
Uma máquina por **categoria** de ferramenta. O nome real da ferramenta (RTK, Graphify, Headroom…) aparece numa plaquinha desenhada pelo código, então uma mesma máquina serve para várias ferramentas da categoria. Cada máquina tem uma imagem parada e uma tira de 3 quadros ligada. Arquivos em `shared/`.

| Categoria | Ferramentas | Máquina |
|---|---|---|
| saída de comandos | RTK, Context Mode, Squeez, Token Saver, lean-ctx, Token Optimizer | Compactador |
| índice de código | Graphify, Serena, CodeGraph, jcodemunch… | Mesa de mapa holográfico |
| proxy | Headroom, Kompact | Portal-filtro |
| memória | claude-mem, TokenEconomizer | Arquivo de cápsulas |
| estilo de resposta | Caveman | Máquina de escrever enxuta |
| MCP genérico | outros servidores MCP | Painel de cabos |

Prompts (depois do estilo + "Single isolated asset…"):

**Compactador — `machine_compactor_idle.png`**
```
A friendly retro-futuristic machine standing against a wall, isometric view: a long sheet of paper printout feeds in from the top, passes through a press with chunky rollers, and comes out as a tiny neat paper cube into a small tray. Metal body in warm gray with teal panels, rounded corners, small dials and indicator lights, a blank small plaque area on the front. Machine turned off, lights dim. Transparent background.
```
**`machine_compactor_on.png`**
```
Same machine as the attached image. Horizontal sprite strip of 3 frames, clear space between them, identical size and position: the machine running, indicator lights glowing teal, rollers pressing, the paper printout going in, a tiny paper cube popping out into the tray. Each frame shows a different moment of the cycle. Transparent background.
```

**Mapa holográfico — `machine_map_idle.png`**
```
A round futuristic table with a dark glass top and a ring of soft lights, isometric view. Above the table, a faint dormant holographic projector lens in the center. Body in dark wood and brushed metal with teal accents, a blank small plaque area on the side. Turned off. Transparent background.
```
**`machine_map_on.png`**
```
Same table as the attached image. Horizontal sprite strip of 3 frames, clear space between them, identical size and position: a glowing teal and purple holographic network graph of connected nodes floating above the table, slowly rotating, with nodes lighting up in sequence. Transparent background.
```

**Portal-filtro — `machine_gateway_idle.png`**
```
A sleek arched gateway device about human height, isometric view, with a vertical funnel of rings in the middle and two side pillars with small screens (blank). Off-white and coral color scheme, a blank small plaque area at the base. Turned off. Transparent background.
```
**`machine_gateway_on.png`**
```
Same gateway as the attached image. Horizontal sprite strip of 3 frames, clear space between them, identical size and position: the rings glowing amber, many small glowing particles flowing in from one side and fewer, brighter particles coming out the other side, as if filtered and condensed. Transparent background.
```

**Arquivo de cápsulas — `machine_memory_idle.png`**
```
A tall cabinet against a wall made of a grid of small round drawers, each with a glass front holding a small capsule, isometric view. Wood and brass with purple accents, a blank small plaque area. Lights off. Transparent background.
```
**`machine_memory_on.png`**
```
Same cabinet as the attached image. Horizontal sprite strip of 3 frames, clear space between them, identical size and position: the capsules glowing soft purple one after another, one drawer sliding open with a glowing capsule rising out of it. Transparent background.
```

**Máquina de escrever enxuta — `machine_terse_idle.png`**
```
A stylish oversized vintage-futuristic typewriter on a small sturdy stand, isometric view, cream body with coral keys and a small pair of brass scissors mechanism on the side. Paper inserted, blank. A blank small plaque area. Turned off. Transparent background.
```
**`machine_terse_on.png`**
```
Same typewriter as the attached image. Horizontal sprite strip of 3 frames, clear space between them, identical size and position: keys moving, the scissors mechanism snipping a long paper strip into a short one, small paper bits falling. Transparent background.
```

**Painel de cabos — `machine_mcp_idle.png`**
```
A wall-mounted patch panel switchboard with rows of round sockets and several colorful coiled cables plugged in, isometric view, dark slate body with small indicator lights, a blank small plaque area. Lights off. Transparent background.
```
**`machine_mcp_on.png`**
```
Same patch panel as the attached image. Horizontal sprite strip of 3 frames, clear space between them, identical size and position: indicator lights blinking in sequence, small sparks of light traveling along the cables. Transparent background.
```

---

## 7. Fichas de tokens e efeitos
Arquivos em `shared/`.

| Arquivo | Prompt (depois do estilo) |
|---|---|
| `tokens.png` | `Four small collectible game items in a row with clear space between them, front view, same size: (1) a blue glowing hexagonal chip, (2) a shiny gold coin with a simple star emboss, (3) a green faceted crystal, (4) a purple faceted crystal. Soft highlights, slight glow. Transparent background.` |
| `vault.png` | `Horizontal sprite strip of 3 frames, clear space between them, identical size and position: a chunky round piggy-bank-shaped safe in brushed teal metal with a coin slot on top and a round dial on the front, isometric view. Frame 1 empty with no coins around, frame 2 a few gold coins piled at its base, frame 3 overflowing with gold coins and sparkles. Transparent background.` |
| `fx_sparkle.png` | `Horizontal sprite strip of 4 frames, clear space between them: a magical sparkle burst effect in gold and white, from a small spark to a full burst with star shapes to fading particles. Transparent background.` |
| `fx_puff.png` | `Horizontal sprite strip of 4 frames, clear space between them: a soft cartoon smoke puff in light teal-gray, from a small puff growing into a round cloud and then dissolving. Transparent background.` |

---

## 8. Ícones dos balões
Um arquivo só, `icons.png`, em `shared/`. O código põe o ícone dentro do balão de fala do personagem.
```
A clean icon set of 12 game UI icons arranged in a 4 by 3 grid with generous equal spacing, same size and same visual weight, flat with soft shading and a subtle outline, colorful but harmonious (teal, coral, amber, purple). Icons, in order: (1) a terminal window with a prompt symbol, (2) an open document page, (3) a pencil writing on a page, (4) a magnifying glass, (5) a globe, (6) a lightbulb with a soft glow, (7) a plug connector, (8) a tiny floating robot head, (9) an hourglass, (10) a green check mark in a circle, (11) an amber warning triangle with no text inside, (12) a stack of coins. No letters or numbers. Transparent background.
```

| Ícone | Quando aparece |
|---|---|
| terminal | Bash / PowerShell / comando |
| documento | leitura de arquivo |
| lápis | edição / escrita |
| lupa | busca (Grep, Glob) |
| globo | busca e leitura na web |
| lâmpada | pensando (resposta longa sem ferramenta) |
| tomada | ferramenta MCP |
| robozinho | criou subagente |
| ampulheta | esperando / sleep / poll |
| check | terminou a tarefa |
| alerta | limite do plano perto do fim |
| moedas | muitos tokens numa só resposta |

---

## Ambientes futuros
Para cada novo tema, repita só a seção 3 trocando a descrição da arte-chave. Ideias:

- `startup` — open space com mesas compridas, paredes de vidro, bean bags, mesa de pingue-pongue.
- `homeoffice` — quarto/escritório em casa, cama ao fundo, janela com chuva, luminária, gato já combina.
- `cafe` — cafeteria com balcão, mesas redondas, quadro de menu sem texto.
- `space` — estação espacial com janela para a Terra, painéis e plantas em cápsulas.

Personagens, robô, gato, máquinas, efeitos e ícones continuam os mesmos.
