import simpy
import plotly.express as px
from collections import namedtuple
import pandas as pd
from random import SystemRandom
import streamlit as st
import base64


#Definicao pagina streamlit
st.title('Bem vindo ao simulador ferroviario!')

st.markdown('Ajuste as configurações a esquerda para prosseguir com a simulação')

#Captura do tempo simulado
tempo_simulado = st.sidebar.slider('Selecione o tempo a ser simulado (u.t)', 1,3000)

#Determinante de saída do regime transitório para permanente
fora_transitorio = st.sidebar.slider('Selecione o instante fora de regime transitório', 0, tempo_simulado)

#Quantidade de setores:
num_setores = st.sidebar.slider('Selecione a quantidade de setores na ferrovia', 2,100)

#Quantidade de trens: Trem0-Setor0-Subindo
num_veiculos = st.sidebar.slider('Selecione a quantidade de trens na ferrovia', 2,10)
origem_veiculos = st.sidebar.multiselect('Selecione a origem dos trens', ['Trem'+str(trem)+'-'+'Setor'+str(setor)+'-'+str(sentido) for trem in range(num_veiculos) for setor in range(num_setores) for sentido in ['Descendo','Subindo'] ] )

#Utilizar efeito de aleatoridade no movimento do trem
fl_aleatoriedade = st.sidebar.radio('Deseja aplicar efeito de aleatoriedade ao longo do movimento do trem?', ('Não', 'Sim'))

if fl_aleatoriedade == 'Sim':
    aleatoriedade = 1
    vl_semente = st.sidebar.slider('Selecione o valor de semente para replicações', 1,100)
    
else:
    aleatoriedade = 0
    vl_semente =  100
    
#Implementacao de indisponibilidade na ferrovia:
fl_indisponibilidade = st.sidebar.radio('Deseja tornar alguma linha da ferrovia indisponível em algum setor?', ('Não', 'Sim'))

if fl_indisponibilidade == "Sim":
    indisponiveis = st.sidebar.multiselect('Selecione os setores com indisponibilidade', [str(setor)+str(tipo) for setor in range(num_setores) for tipo in ['A','B']] )
else:
    indisponiveis = []

#Botao para iniciar a simulacao
simule = st.sidebar.button('Pressione para simular')




LOG_TELA = 0                #Ativa log em tela
num_trens = 0               #Numero de trens criados
fila_unidade_controle = []  #Fila de requisições para liberação pelo UnidadeControle
ferrovia_linha = []         #Estrutura de sb's na ferrovia 
ferrovia_travessao = []     #Estrutura de travessao ferrovia
dados = []                #dados para plotagem em gráfico
registros_transit_time = []


#Instancia de aleatorieade
random = SystemRandom()

random.seed(vl_semente)

#Estrutura de tupla para dados do gráfico de trem
dados_trem = namedtuple('Dados','setor instante thp nome')

#Constante para vetores de controle
SB_A = 0
SB_B = 1

T1 = 0
T2 = 1
T3 = 2

FERR_RECURSO = 0
FERR_DIR = 1
FERR_REQ = 2
FERR_TREM = 3

matriz_criterios = [
    [2,0,0,0, -2,0], 
    [1,1,0,0, 0,0],  
    [1,0,1,0,  1,0],  
    [1,0,0,1, -1,0], 
    [0,2,0,0,  0,1],  
    [0,1,1,0,  1,0],
    [0,1,0,1, 0,1],
    [0,0,2,0, 2,0], 
    [0,0,1,1,  1,0], 
    [0,0,0,2,  0,1]  
]

df_criterios = pd.DataFrame(
    data=matriz_criterios,
    columns=('Disponivel',
             'Indisponivel',
             'Trem_mesmo_sent', 
             'Trem_sent_oposto', 
             'Iterador',
             'Flag_break')
)

if simule:
    
    #Funcao print
    def printf(texto):
        if LOG_TELA == 1:
            print(texto)
    
    #Funcao geradora de movimentos        
    def timeOut(movimento):
        
        if aleatoriedade == 1:
            dist_movimento = random.triangular(low=0,high=10,mode=5)
            dist_lib_cauda = random.triangular(low=0,high=2,mode=1)
            
        else:
            dist_movimento = 5
            dist_lib_cauda = 1
        
        return{
            'deslocamento': dist_movimento,
            'liberar_cauda': dist_lib_cauda
            }.get(movimento, 0.0)
        
            
    def GerarPlotagem():
        
        global ferrovia_linha, df
        
        df = pd.DataFrame(data=dados, columns=('setor','instante', 'thp','nome')) \
            .drop(columns = ['thp']) \
            .set_index(['nome']) \
            .apply(lambda x: x.apply(pd.Series).stack()) \
            .reset_index() \
            .drop('level_1', 1) \
            .rename(columns={'nome': 'Trem'})
               
        figura = px.line(df, x="instante", y="setor", color='Trem' )
        
        return figura
        
    
    def GerarEstatisticas():
        
        global statistics_df, href
        
        transit_medio = sum(registros_transit_time)/len(registros_transit_time)
        
        statistics_df = (
                      pd.DataFrame(data=dados, columns=('Setor', 'Instante', 'THP','Trem'))
                     .drop(columns = ['Setor', 'Instante'])
                     .explode('THP')
                     .groupby('Trem').agg({'THP':'sum'})
                     )
         

        transit_medio_column = [transit_medio for linha in range(len(statistics_df))]      
        statistics_df['Transit_Time_Medio_Geral'] = transit_medio_column
        
        csv = statistics_df.to_csv(index=False)
        b64 = base64.b64encode(csv.encode()).decode()  
        href = f'<a href="data:file/csv;base64,{b64}">Download CSV File</a> (Clique com botão direito para fazer o download das estatisticas da simulação selecionando "salvar link" como &lt;nome_do_arquivo.csv&gt;)'
        st.markdown(href, unsafe_allow_html=True)



    def ArmazenarPosicao(id_trem, setor):
        dados[id_trem-1].setor.append(setor)
    
    
    def ArmazenarInstante(id_trem, env):
        dados[id_trem-1].instante.append(env.now)
        
   
    def AtualizarRequisicoes():
        global unidade_controle_event
        if not unidade_controle_event.triggered:
            unidade_controle_event.succeed()



    #Configurador da ferrovia
    def ConfigurarFerrovia(env):
        
        global ferrovia, ferrovia_travessao,num_setores
        printf("Criando pares de SBs da ferrovia...")
        
        for setor in range(num_setores):
            data = dict()
            data2 = dict()
            #id = id da seção da bloqueio
            #sb = coleção das duas SBs da seção
            data2.update(id = setor,\
                         TRAVESSAO = [[simpy.Resource(env,1),0,0,0],\
                                    [simpy.Resource(env,1),0,0,0],\
                                    [simpy.Resource(env,1),0,0,0]])        
            data.update(id = setor, \
                        LINHA = [[simpy.Resource(env,1),0,0,0],\
                              [simpy.Resource(env,1),0,0,0]])
            ferrovia_linha.append(data)
            ferrovia_travessao.append(data2)
        printf("Foram criados %s pares de SBs!" % (num_setores))    
    
    
    
    
    #Processo da unidade de controle
    def UnidadeControle(env):
        global unidade_controle_event,ferrovia,num_setores
        
        def AnalisarFluxo(prox_setor,num_setores,dir,id_trem):
            
            #Variavel do status de fluxo: {0:fechado, 1:aberto}
            fluxo_aberto = 1
            
            #Variavel auxiliar de identificacao do proximo setor
            aux_prox_setor = prox_setor                                    
            contador = 1
            
            #Setor seguinte inteiro ocupado
            if ferrovia_linha[aux_prox_setor]["LINHA"][SB_A][FERR_RECURSO].count == 1 and \
                ferrovia_linha[aux_prox_setor]["LINHA"][SB_B][FERR_RECURSO].count == 1:
                printf("Bloqueia trem %d " % (id_trem))
                fluxo_aberto = 0
                return fluxo_aberto
            
            #Analise de deferimento
            if fluxo_aberto == 1 and aux_prox_setor>=0 and aux_prox_setor <= num_setores:         
                while contador >= 1:
                    
                    #Contabilizar as quatro variáveis
                    qtd_linha_disponivel = sum(1 for setor in [ ferrovia_linha[aux_prox_setor]["LINHA"][SB_A], ferrovia_linha[aux_prox_setor]["LINHA"][SB_B] ] if setor[FERR_RECURSO].count== 0)
                    qtd_linha_indisponivel = sum(1 for setor in [ ferrovia_linha[aux_prox_setor]["LINHA"][SB_A], ferrovia_linha[aux_prox_setor]["LINHA"][SB_B] ] if setor[FERR_RECURSO].count== 1 and setor[FERR_TREM] == 0)
                    qtd_trem_mesmo_sentido = sum(1 for setor in [ ferrovia_linha[aux_prox_setor]["LINHA"][SB_A], ferrovia_linha[aux_prox_setor]["LINHA"][SB_B] ] if setor[FERR_RECURSO].count== 1 and setor[FERR_DIR] == dir)
                    qtd_trem_sentido_oposto = sum(1 for setor in [ ferrovia_linha[aux_prox_setor]["LINHA"][SB_A], ferrovia_linha[aux_prox_setor]["LINHA"][SB_B] ] if setor[FERR_RECURSO].count== 1 and setor[FERR_DIR] != dir and setor[FERR_DIR] != 0)
                    
                    
                    #Buscar na tabela o incremento e o break:
                    try:
                        criterio_decisao = df_criterios.query('Disponivel == qtd_linha_disponivel & Indisponivel==qtd_linha_indisponivel & Trem_mesmo_sent==qtd_trem_mesmo_sentido & Trem_sent_oposto ==qtd_trem_sentido_oposto')
                        aux_iterador = int(criterio_decisao.Iterador)
                        aux_break = int(criterio_decisao.Flag_break)
                    except:
                        printf('Erro de lookup em criterios')
                        break
                    
            
                    #Atualizar o break
                    if aux_break == 1:
                        fluxo_aberto = 0
                        break
                    
                    #Atualizar o incremento
                    elif aux_break == 0:
                        contador = contador + aux_iterador
                        
                    #Espaco livre ao progresso
                    if contador <= 0: 
                        fluxo_aberto = 1
                        break
                
                    #Loop para proxima verificacao
                    aux_prox_setor = aux_prox_setor + dir
                    
                    #Chegou na mina ou no porto
                    if aux_prox_setor == -1 or aux_prox_setor == num_setores:
                        fluxo_aberto = 1
                        break
                                    
                    #Verificacao de adesao a estrututura ferrea
                    if aux_prox_setor >= num_setores or aux_prox_setor == -1:
                        fluxo_aberto = 0
                        break
                    
            return fluxo_aberto
      
        
        while(True):
            
            #Cria próximo evento "unidade_controle_event"
            unidade_controle_event = env.event() 
           
            #Aguarda disparar evento "unidade_controle_event"
            yield unidade_controle_event
            
            #Verifica cada trem do sistema a condição de avançar
            remove = []
            
            for requisicao in fila_unidade_controle:
                id_trem = requisicao[0]
                evento_liberacao = requisicao[1]["evento"]
                prox_setor = requisicao[1]["prox_setor"]
                dir = requisicao[1]["dir"]
                tipo_sb = requisicao[1]["tipo_sb"]
    
                printf('analisando requisicao trem %d prox_setor %d dir %d' % (id_trem,prox_setor,dir))            
    
                ocupa = 1
                            
                #Limita ao contexto do trem em movimento
                if prox_setor<num_setores and prox_setor>=0:
                                        
                    if AnalisarFluxo(prox_setor,num_setores,dir,id_trem) == 0:
                        ocupa = 0
                        
                        if env.now > fora_transitorio:
                            #Representacao de trem parado
                            setor_atual = prox_setor - dir
                            ArmazenarPosicao(id_trem, setor_atual)
                            ArmazenarInstante(id_trem, env)

                            
                    else:
                        ocupa = 1
                        
    
                        #Requisita recurso de sb 0
                        if ferrovia_linha[prox_setor]["LINHA"][SB_A][FERR_RECURSO].count == 0:
                           ferrovia_linha[prox_setor]["LINHA"][SB_A][FERR_REQ] = \
                               ferrovia_linha[prox_setor]["LINHA"][SB_A][FERR_RECURSO].request()
                           ferrovia_linha[prox_setor]["LINHA"][SB_A][FERR_DIR] = dir
                           ferrovia_linha[prox_setor]["LINHA"][SB_A][FERR_TREM] = id_trem
                           sb = SB_A
                           print("%d   @@ Alocado recurso SB A do eh #%s para trem #%s" % (env.now,prox_setor,id_trem));
                           
                        #Requisita recurso de sb 1
                        elif ferrovia_linha[prox_setor]["LINHA"][SB_B][FERR_RECURSO].count == 0:
                           ferrovia_linha[prox_setor]["LINHA"][SB_B][FERR_REQ] = \
                               ferrovia_linha[prox_setor]["LINHA"][SB_B][FERR_RECURSO].request()
                           ferrovia_linha[prox_setor]["LINHA"][SB_B][FERR_DIR] = dir
                           ferrovia_linha[prox_setor]["LINHA"][SB_B][FERR_TREM] = id_trem
                           sb = SB_B
                           print("%d   @@ Alocado recurso SB B do eh #%s para trem #%s" % (env.now,prox_setor,id_trem));
                  
                    
                        #Libera trem
                        evento_liberacao.succeed([sb])
                        remove.append(fila_unidade_controle.index(requisicao))
                    
                            
            #Remocao da solicitacao a fila de analise
            for index in sorted(remove, reverse=True):
                del fila_unidade_controle[index]
                              
        
    #Processo da entidade "trem"
    def Trem(env, out, setor, sb, dir):
        global num_trens, fila_unidade_controle,dados,origem_trens
      
        #sb: seção de bloqueio que o trem está localizado
        #dir: direção em que o trem está seguindo {-1:descendo,1:subindo}
        #out: trem fora da ferrovia {0:Dentro,1:Fora}
        
        criado_em = env.now #Momento de criação do trem
        num_trens += 1      #Id do novo trem criado
        id_trem = num_trens #Referencia de trem
        sb = 2              #Instanciar o tipo de sb
        thp_inicio = -1
        
        #Instante de última saida do porto
        chegada_porto = - 1
        
        #Gera estrutura de dados para a entidade
        dados.append(dados_trem([],[],[],"Trem_#" + str(id_trem)))
        
        printf("   Trem #%s criado " % (id_trem) )
        AtualizarRequisicoes() 
        
        while(True):
            
            #Instancia o trem na ferrovia, coleta primeiro setor
            if(out == 1):
                prox_setor = setor
            else:
                prox_setor = setor + dir
    
            #Caso trem esteja em movimentação:
            if(out==0 and prox_setor>=0 and prox_setor<num_setores):
                
                if env.now > fora_transitorio:
                    ArmazenarPosicao(id_trem, setor)
                    ArmazenarInstante(id_trem, env)
                           
      
            #Passagem de informacoes a unidade controladora
            aguarda_unidade_controle = env.event()
            fila_unidade_controle.append(
                [
                    id_trem,
                    dict(
                        evento = aguarda_unidade_controle,
                        prox_setor = prox_setor,
                        dir = dir,
                        tipo_sb = sb
                    )
                ])
            
            
            #Montagem do Transit Time a partir do local da unidade demandante
            if out==1 and setor == 0:
                
              
                if chegada_porto == -1:
                    chegada_porto = env.now
                    
                else:
                    TT = env.now - chegada_porto
                    
                    if env.now > fora_transitorio:
                        registros_transit_time.append(TT)
                    
                    chegada_porto = env.now
        
            
            #Inicio da contagem THP
            if env.now > fora_transitorio:
                thp_inicio = env.now
            
            printf("   Trem #%s aguardando liberação pelo UnidadeControle" % (id_trem) )   
            AtualizarRequisicoes()
            
            #Aguarda UnidadeControle liberar o trem para seguir
            yield aguarda_unidade_controle
            
            #Montagem do indicador THP
            if env.now > fora_transitorio and thp_inicio != -1:
                thp = env.now - thp_inicio
            
                #Armazenamento do THP
                if thp > 0:
                    dados[id_trem-1].thp.append(thp)
                
            #Atualizacao de setor
            sb_ant = sb
            
            #Retorno da unidade de controle sobre proximo tipo de SB
            r = aguarda_unidade_controle.value
            sb = r[0]
    
    
            printf("   Trem #%s liberado pelo UnidadeControle para seguir até setor #%s na sb #%s" % (id_trem, prox_setor, sb) )
            
            #Trem já se encontra no trecho
            if(out==0):           
                if dir==-1: id_travessao = prox_setor+1
                elif dir==1: id_travessao = prox_setor           
                
                #Condicao pre determinada
                condicao = 0
                
                #Alocacao de travessoes (Ti)
                if ( sb_ant == SB_A and sb == SB_A ):
                    req1 = ferrovia_travessao[id_travessao]["TRAVESSAO"][T1][FERR_RECURSO].request()
                    yield req1
                    condicao = 0
                elif (sb_ant == SB_B and sb == SB_B): 
                    req2 = ferrovia_travessao[id_travessao]["TRAVESSAO"][T2][FERR_RECURSO].request()
                    yield req2
                    condicao = 1
                else:
                    req3 = ferrovia_travessao[id_travessao]["TRAVESSAO"][T3][FERR_RECURSO].request()
                    req1 = ferrovia_travessao[id_travessao]["TRAVESSAO"][T1][FERR_RECURSO].request()
                    req2 = ferrovia_travessao[id_travessao]["TRAVESSAO"][T2][FERR_RECURSO].request()
                    yield req3
                    yield req1
                    yield req2
                    condicao = 2
                    
                                        
                printf("   Trem #%s iniciou deslocamento pela singela" % (id_trem))
                
                #Marco de inicio de deslocamento
                if env.now > fora_transitorio:
                    ArmazenarPosicao(id_trem, setor)
                    ArmazenarInstante(id_trem, env)

                
                #Tempo deslocamento na singela até liberar setor
                yield env.timeout(timeOut('deslocamento'))
                printf("   Trem #%s liberou setor anterior #%s em %s min" % (id_trem, setor, env.now)) 
            
                if(setor>=0 and setor < num_setores):
                    ferrovia_linha[setor]["LINHA"][sb_ant][FERR_RECURSO].release(\
                                                    ferrovia_linha[setor]["LINHA"][sb_ant][FERR_REQ])
                
                AtualizarRequisicoes()
                
                yield env.timeout(timeOut('liberar_cauda'))
                        
                #Momento para desalocar os Ti
                if condicao == 0:
                    ferrovia_travessao[id_travessao]["TRAVESSAO"][T1][FERR_RECURSO].release(req1)          
                elif condicao == 1:
                    ferrovia_travessao[id_travessao]["TRAVESSAO"][T2][FERR_RECURSO].release(req2)  
                else:
                    ferrovia_travessao[id_travessao]["TRAVESSAO"][T3][FERR_RECURSO].release(req3)               
                    ferrovia_travessao[id_travessao]["TRAVESSAO"][T2][FERR_RECURSO].release(req2)               
                    ferrovia_travessao[id_travessao]["TRAVESSAO"][T1][FERR_RECURSO].release(req1)               
                    
         
                setor = prox_setor
                                    
                if setor == num_setores - 1 and dir == 1:
                    #Chegada a unidade de suprimento            
                    print("Trem %d chegou a unidade de suprimento %d" % (id_trem,env.now))     
                    
                    if env.now > fora_transitorio:
                        ArmazenarPosicao(id_trem, setor)
                        ArmazenarInstante(id_trem, env)
                   
                    yield env.timeout(timeOut('deslocamento')) #timeout(5)
    
                    if env.now > fora_transitorio:
                        ArmazenarPosicao(id_trem, setor+1)
                        ArmazenarInstante(id_trem, env)

                    yield env.timeout(timeOut('deslocamento')) #timeout(5)
    
                    if env.now > fora_transitorio:                
                        ArmazenarPosicao(id_trem, setor+1)
                        ArmazenarInstante(id_trem, env)
                        
                    printf("   Trem #%s chegou no destino subindo (mina) " % (id_trem)) 
                    ferrovia_linha[setor]["LINHA"][sb][FERR_RECURSO].release(\
                                ferrovia_linha[setor]["LINHA"][sb][FERR_REQ])
                    out = 1
                    dir = -1
    
                elif setor == 0 and dir == -1:
                    #Chegada a unidade demandante            
                    print("Trem %d chegou a unidade demandante %d" % (id_trem,env.now))                
                    
                    if env.now > fora_transitorio:
                        ArmazenarPosicao(id_trem, 0)
                        ArmazenarInstante(id_trem, env)                            

                    yield env.timeout(timeOut('deslocamento')) 
    
                    if env.now > fora_transitorio:
                        ArmazenarPosicao(id_trem, -1)
                        ArmazenarInstante(id_trem, env) 
    
                    yield env.timeout(timeOut('deslocamento')) 
                    
                    if env.now > fora_transitorio:
                        ArmazenarPosicao(id_trem, -1)
                        ArmazenarInstante(id_trem, env) 
                    
                    printf("   Trem #%s chegou no destino descendo (porto) " % (id_trem)) 
                    ferrovia_linha[setor]["LINHA"][sb][FERR_RECURSO].release(\
                                ferrovia_linha[setor]["LINHA"][sb][FERR_REQ])
                    out = 1
                    dir = 1
                    
            #Trem não se encontra no trecho: zona externa
            else:
                out = 0
                #Tempo deslocamento para chegar até setor
                yield env.timeout(timeOut('deslocamento'))  
              
       
    
    env = simpy.Environment()
    ConfigurarFerrovia(env)
    env.process(UnidadeControle(env))
  
    #Indisponibiliza setores
    for setor_ind in indisponiveis:
        nu_setor = int(setor_ind[0])
        
        if setor_ind[1] == 'A':
            tp_setor = 0
        else:
            tp_setor = 1
               
        ferrovia_linha[nu_setor]["LINHA"][tp_setor][FERR_RECURSO].request()
  
    
    #Dispoe processos dos trens  
    for veiculo in origem_veiculos:
       
        #Extracao do sentido
        delimitador1 = veiculo.find('-',0) + 1
        delimitador2 = veiculo.find('-',delimitador1)+1
        
        setor_inicio = veiculo.find('Setor') + 5
        
        setor_origem = int(veiculo[ setor_inicio:delimitador2-1 ])
        sentido = veiculo[delimitador2+1:]
                
        if sentido == "Subindo":
            direcao = -1
        else:
            direcao = +1
        
        env.process(Trem(env=env,out=1,setor=setor_origem,dir=direcao,sb=-1))

        
        
    
    #Executa simulacao:  
    ult_now = -1
    while True:
        if not ult_now == env.now:
            printf("### New event notice at t=%s:" % (env.now))
            ult_now = env.now
    
        tEvt = env.peek()
        if env.now < tempo_simulado:
            try:
                env.step()
            except simpy.core.EmptySchedule:
                printf("Término prematuro: Não há mais eventos futuros")
                break
                pass
        else:
            break
    
        
    st.plotly_chart(GerarPlotagem(), use_container_width=True)
    GerarEstatisticas()
    st.dataframe(data=statistics_df)
    
    