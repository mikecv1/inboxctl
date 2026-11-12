# inboxctl: limpe sua caixa de e-mail do Outlook / Hotmail em 10 minutos

O inboxctl é um programinha que roda no seu computador. Ele lê sua caixa de entrada, mostra quem mais te manda e-mail, e deixa você escolher de quem quer se livrar. Você marca, ele descadastra, bloqueia e limpa. Nada é apagado de verdade: tudo vai para a pasta "Itens Excluídos", de onde dá para recuperar.

Funciona com contas @outlook.com, @hotmail.com, @live.com e @msn.com.

Nada sai do seu computador. Não tem servidor, não tem cadastro, ninguém vê seus e-mails. O programa fala direto com a Microsoft, na sua conta, com a sua permissão.

## Passo a passo (Windows)

**1. Baixar**

Abra https://github.com/mikecv1/inboxctl/releases/latest e clique em `inboxctl.exe`. Salve na pasta Downloads.

**2. Abrir**

Dê dois cliques no `inboxctl.exe`.

Na primeira vez o Windows mostra uma tela azul "O Windows protegeu o PC". Isso aparece para qualquer programa pequeno que não paga certificado de assinatura. Clique em **Mais informações** e depois em **Executar assim mesmo**.

Espere uns 15 segundos. Uma aba vai abrir no seu navegador com a tela do inboxctl. Se não abrir, digite na barra de endereço: `127.0.0.1:8765`

**3. Conectar sua conta**

Clique em **Connect Microsoft account**. Vai abrir a página de login da Microsoft. Entre com seu e-mail e senha normais e clique em **Aceitar** nas permissões (ler e mover e-mails, enviar e-mail, criar regras). Depois volte para a aba do inboxctl.

Se a página de login não abrir ou travar, clique em **Use a code instead** e siga o que aparece na tela.

**4. Esperar o scan**

Assim que conectar, o programa começa a ler sua caixa sozinho. Uma caixa com 10 mil e-mails leva uns 5 minutos; com 50 mil, uns 20. Pode deixar aberto e ir fazer outra coisa.

**5. Escolher e limpar**

Vai aparecer uma lista de remetentes, do que mais manda para o que menos manda.

- Marque a caixinha de quem você quer se livrar.
- Deixe marcado **Unsubscribe** (descadastrar) e **Block future mail** (bloquear os próximos).
- Se quiser apagar o que já está na caixa, marque também **Move existing mail to Deleted Items**.
- Clique em **Apply to selected** e confirme.

Pronto. Repita com outros remetentes quando quiser.

## Dicas

- Comece pelos grandes: use o filtro **25+ messages** e olhe os 20 primeiros. Em geral são 80% do lixo.
- Banco, cartão, companhia aérea, iFood, Uber: eles mandam propaganda e também coisas importantes do mesmo endereço. Descadastre, mas não bloqueie.
- Remetente que parou de mandar há anos não precisa de descadastro, só de limpeza (marque só **Move existing mail to Deleted Items**).
- Tem alguém que você quer proteger de qualquer engano? Marque e clique em **Mark as keep**. Ele some da lista e nunca entra no "marcar todos".
- A coluna **Unsubscribe** diz como cada um pode ser descadastrado:
  - `one-click`: automático e confiável
  - `mailto`: o programa manda um e-mail de descadastro por você
  - `link`: só tem um link, o programa abre para você clicar
  - `none`: não tem descadastro, só dá para bloquear e limpar

## Para fechar

Clique em **Quit** na tela do inboxctl, ou feche a aba e encerre o programa pelo ícone na barra de tarefas. Para usar de novo, é só abrir o `inboxctl.exe` outra vez: ele lembra seu login.

## Perguntas comuns

**É seguro?** O código é aberto e está em https://github.com/mikecv1/inboxctl. O programa roda só no seu computador e só mexe na sua conta com a permissão que você deu. Você pode tirar essa permissão a qualquer hora em https://account.microsoft.com/privacy/app-access

**Apaguei algo por engano.** Olhe a pasta "Itens Excluídos" no Outlook. Está tudo lá até você esvaziar.

**Quero desfazer um bloqueio.** No Outlook: Configurações, E-mail, Regras. As regras do inboxctl começam com "inboxctl block:". Apague a que quiser.

**O antivírus reclamou.** É falso positivo comum em programas feitos com Python e empacotados em um único .exe. Se preferir não arriscar, não use, sem problema.

**Tenho Gmail.** Ainda não funciona. Está no plano.

Dúvidas: fala com o Mike.
