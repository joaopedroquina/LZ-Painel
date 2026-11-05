# LZ Painel — Gerar Painel.exe pelo GitHub (sem instalar Python)

Este pacote utiliza a versao que voce enviou: `app(20261105-015307).py`, `index(5).html` e `icone.ico`. O arquivo `.exe` NAO esta dentro deste ZIP: ele sera compilado pelo GitHub Actions num computador Windows e liberado para download quando a execucao terminar.

## PASSO A PASSO (pelo navegador)

1. Entre em https://github.com e faca login (ou crie sua conta).
2. No botao **+** > **New repository**, coloque um nome como `lz-painel-windows`. Prefira **Private** se nao quiser tornar o codigo publico. Crie o repositorio.
3. **Extraia este ZIP no seu computador. Nao envie o arquivo ZIP para o GitHub.**
4. No repositorio, clique **Add file > Upload files**. Envie apenas os arquivos da pasta principal `app.py`, `index.html`, `icone.ico`, `requirements.txt` e `README.md`. Clique em **Commit changes**.
5. No GitHub, clique **Add file > Create new file**. No campo do nome, digite exatamente `.github/workflows/gerar-exe.yml` (o GitHub cria as pastas automaticamente).
6. Abra o arquivo `WORKFLOW_PARA_COPIAR.txt` que esta neste ZIP, copie TODO o texto dele e cole no editor do arquivo `gerar-exe.yml`. Clique em **Commit changes**.
7. Entre na aba **Actions**, selecione **Gerar LZ Painel EXE** e clique **Run workflow > Run workflow**. Se a execucao comecar automaticamente apos salvar, pode usar essa execucao.
8. Abra a execucao que terminou com um sinal verde. No final da pagina, em **Artifacts**, clique em **LZ-Painel-EXE-Windows** e baixe o ZIP disponibilizado pelo GitHub.
9. Extraia o ZIP baixado do GitHub. Dentro dele estara o arquivo **Painel.exe**. O Python nao precisara estar instalado no computador onde voce executar o programa.

Se nao aparecer a opcao Run workflow, confira se o arquivo `.github/workflows/gerar-exe.yml` esta na branch principal (main) e se Actions esta habilitado nas configuracoes do repositorio.

## Outra forma (com GitHub Desktop)

Se souber usar Git, adicione a pasta inteira do projeto a um repositorio e faca push da branch principal. A estrutura de `.github/workflows/gerar-exe.yml` ja esta pronta e dispara a compilacao automaticamente.

## Sobre o aplicativo

- O app inclui a interface HTML e o icone enviados, sem modificar o painel original.
- A compilacao usa PyInstaller, pywebview e psutil em ambiente Windows do GitHub.
- O programa compilado pede permissao de administrador, pois o codigo pode alterar servicos e configuracoes do Windows.
- Pode ser necessario ter Microsoft Edge WebView2 Runtime no PC (normalmente ja existe em Windows atualizado).
- Antes de usar funcoes de otimizacao que alteram servicos, crie um ponto de restauracao.
- O executavel nao e assinado digitalmente; nao distribua sem testar e verificar a seguranca do arquivo.
- O GitHub pode impor limites/cobrancas de Actions dependendo da conta e do repositorio; verifique antes de usar.
- O primeiro build pode falhar por mudancas de dependencias; consulte a aba Actions para ler o erro. Este pacote foi validado estaticamente, mas ainda nao foi testado num runner Windows.
