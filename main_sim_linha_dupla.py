import simpy
import plotly.express as px
from collections import namedtuple
import pandas as pd
from random import SystemRandom
import streamlit as st
import base64



#Def pagina streamlit
st.title('Bem vindo ao simulador ferroviario!')

st.markdown('Desenvolvida com SimPy, esta aplicação permite simular ferrovias do tipo dupla e singela.\
        Entretanto, é importante ressaltar algumas considerações quanto a solução:')

#Captura do tempo simulado
tempo_simulado = st.sidebar.slider('Selecione o tempo a ser simulado (u.t)', 1,3000)

#Determinante de saída do regime transitório para permanente
fora_transitorio = st.sidebar.slider('Selecione o instante fora de regime transitório', 0, tempo_simulado)

#Quantidade de setores:
num_setores = st.sidebar.slider('Selecione a quantidade de setores na ferrovia', 2,100)

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

#Selecao de extracao de arquivo de estatisticas da simulacao


#Botao para iniciar a simulacao
simule = st.sidebar.button('Pressione para simular')

cenario = 'Figura 37'

LOG_TELA = 0                #Ativa log em tela
num_trens = 0               #Numero de trens criados
CCO_queue = []              #Fila de requisições para liberação pelo CCO
ferrovia_linha = []         #Estrutura de sb's na ferrovia 
ferrovia_travessao = []     #Estrutura de travessao ferrovia
valores = []                #Valores para plotagem em gráfico
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
             'X',
             'Break')
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
        
            
    def fim_simulation():
        
        global ferrovia_linha, df
        
        df = pd.DataFrame(data=valores, columns=('setor','instante', 'thp','nome')) \
            .drop(columns = ['thp']) \
            .set_index(['nome']) \
            .apply(lambda x: x.apply(pd.Series).stack()) \
            .reset_index() \
            .drop('level_1', 1)
               
        figura = px.line(df, x="instante", y="setor", color='nome' )
        
        return figura
        
    
    def gerar_estatisticas():
        
        global statistics_df, href
        
        transit_medio = sum(registros_transit_time)/len(registros_transit_time)
        
        statistics_df = (
                      pd.DataFrame(data=valores, columns=('Setor', 'Instante', 'THP','Trem'))
                     .drop(columns = ['Setor', 'Instante'])
                     .explode('THP')
                     .groupby('Trem').agg({'THP':'sum'})
                     )
         
        cenario_column = [cenario for linha in range(len(statistics_df))]
        transit_medio_column = [transit_medio for linha in range(len(statistics_df))]
        
        statistics_df['Cenario'] = cenario_column
        statistics_df['Transit_Time_Medio_Geral'] = transit_medio_column
        
        csv = statistics_df.to_csv(index=False)
        b64 = base64.b64encode(csv.encode()).decode()  
        href = f'<a href="data:file/csv;base64,{b64}">Download CSV File</a> (Clique com botão direito para fazer o download das estatisticas da simulação selecionando "salvar link" como &lt;nome_do_arquivo.csv&gt;)'
        st.markdown(href, unsafe_allow_html=True)

        
        #variavel statist
        statistics_df.to_csv(r'statistic_file_log', header=True, index=True, sep=',', mode='a')
    
    
    #Processo da unidade de controle
    def CCO(env):
        global CCO_event,ferrovia,num_setores,trem_pass
        
        def analise_fluxo(prox_setor,num_setores,dir,id_trem):
                    
            fluxo_aberto = 1
            aux = prox_setor
                                    
            contador = 1
            
            #Setor seguinte inteiro ocupado
            if ferrovia_linha[aux]["LINHA"][SB_A][FERR_RECURSO].count == 1 and \
                ferrovia_linha[aux]["LINHA"][SB_B][FERR_RECURSO].count == 1:
                print("Bloqueia trem %d " % (id_trem))
                fluxo_aberto = 0
                return fluxo_aberto
            
            #Analise de deferimento
            if fluxo_aberto == 1 and aux>=0 and aux <= num_setores:#-1:         
                while contador >= 1:
                    
                    #Contabilizar as quatro variáveis
                    qtd_linha_disponivel = sum(1 for setor in [ ferrovia_linha[aux]["LINHA"][SB_A], ferrovia_linha[aux]["LINHA"][SB_B] ] if setor[FERR_RECURSO].count== 0)
                    qtd_linha_indisponivel = sum(1 for setor in [ ferrovia_linha[aux]["LINHA"][SB_A], ferrovia_linha[aux]["LINHA"][SB_B] ] if setor[FERR_RECURSO].count== 1 and setor[FERR_TREM] == 0)
                    qtd_tren_mesmo_sentido = sum(1 for setor in [ ferrovia_linha[aux]["LINHA"][SB_A], ferrovia_linha[aux]["LINHA"][SB_B] ] if setor[FERR_RECURSO].count== 1 and setor[FERR_DIR] == dir)
                    qtd_tren_sentido_oposto = sum(1 for setor in [ ferrovia_linha[aux]["LINHA"][SB_A], ferrovia_linha[aux]["LINHA"][SB_B] ] if setor[FERR_RECURSO].count== 1 and setor[FERR_DIR] != dir and setor[FERR_DIR] != 0)
                    
                    
                    #Buscar na tabela o incremento e o break:
                    try:
                        f1 = df_criterios[df_criterios['Disponivel'] == qtd_linha_disponivel]
                        f2 = f1[f1['Indisponivel'] == qtd_linha_indisponivel]
                        f3 = f2[f2['Trem_mesmo_sent'] == qtd_tren_mesmo_sentido]
                        f4 = f3[f3['Trem_sent_oposto'] == qtd_tren_sentido_oposto]
                        var_x = int(f4.X)
                        var_break = int(f4.Break)
                    except:
                        printf('Erro de lookup em criterios')
                        break
                    
            
                    #Atualizar o break
                    if var_break == 1:
                        fluxo_aberto = 0
                        break
                    
                    #Atualizar o incremento
                    elif var_break == 0:
                        contador = contador + var_x
                        
                    #Espaco livre ao progresso
                    if contador <= 0: 
                        fluxo_aberto = 1
                        break
                
                    #Loop para proxima verificacao
                    aux = aux + dir
                    
                    #Chegou na mina ou no porto
                    if aux == -1 or aux == num_setores:
                        fluxo_aberto = 1
                        break
                                    
                    #Verificacao de adesao a estrututura ferrea
                    if aux >= num_setores or aux == -1:
                        fluxo_aberto = 0
                        break
                    
            return fluxo_aberto
      
        
        while(True):
            
            #Cria próximo evento "CCO_event"
            CCO_event = env.event() 
           
            #Aguarda disparar evento "CCO_event"
            yield CCO_event
            
            #Verifica cada trem do sistema a condição de avançar
            remove = []
            
            for requisicao in CCO_queue:
                id_trem = requisicao[0]
                evento_liberacao = requisicao[1]["evento"]
                prox_setor = requisicao[1]["prox_setor"]
                dir = requisicao[1]["dir"]
                tipo_sb = requisicao[1]["tipo_sb"]
    
                printf('analisando requisicao trem %d prox_setor %d dir %d' % (id_trem,prox_setor,dir))            
    
                ocupa = 1
                            
                #Limita ao contexto do trem em movimento
                if prox_setor<num_setores and prox_setor>=0:
                                        
                    if analise_fluxo(prox_setor,num_setores,dir,id_trem) == 0:
                        ocupa = 0
                        
                        if env.now > 1000:
                            #Representacao de trem parado
                            setor_atual = prox_setor - dir
                            valores[id_trem-1].setor.append(setor_atual)
                            valores[id_trem-1].instante.append(env.now)
                            
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
                        remove.append(CCO_queue.index(requisicao))
                    
                            
            #Remocao da solicitacao a fila de analise
            for index in sorted(remove, reverse=True):
                del CCO_queue[index]
                  
    def Trigger_CCO():
        global CCO_event
        if not CCO_event.triggered:
            CCO_event.succeed()
            
        
    #Processo da entidade "trem"
    def trem(env, out, setor, sb, dir):
        global num_trens, CCO_queue,valores,origem_trens
      
        #sb: seção de bloqueio que o trem está localizado
        #dir: direção em que o trem está seguindo {-1,1}
        #out: trem fora da ferrovia {0,1}
        
        criado_em = env.now #Momento de criação do trem
        num_trens += 1      #Id do novo trem criado
        id_trem = num_trens #Referencia de trem
        sb = 2              #Instanciar o tipo de sb
        thp_inicio = -1
        
        #Instante de última saida do porto
        chegada_porto = - 1
        
        
        valores.append(dados_trem([],[],[],"Trem_#" + str(id_trem)))
        printf("   Trem #%s criado " % (id_trem) )
        Trigger_CCO() 
        
        while(True):
            #Instancia o trem na ferrovia, coleta primeiro setor
            if(out == 1):
                prox_setor = setor
            else:
                prox_setor = setor + dir
    
            #Caso trem esteja em movimentação:
            if(out==0 and prox_setor>=0 and prox_setor<num_setores):
                
                if env.now > fora_transitorio:
                    valores[id_trem-1].setor.append(setor)
                    valores[id_trem-1].instante.append(env.now)
                           
      
            #Passagem de informacoes a unidade controladora
            aguarda_CCO = env.event()
            CCO_queue.append(
                [
                    id_trem,
                    dict(
                        evento = aguarda_CCO,
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
            
            printf("   Trem #%s aguardando liberação pelo CCO" % (id_trem) )   
            Trigger_CCO()
            
            #Aguarda CCO liberar o trem para seguir
            yield aguarda_CCO
            
            #Montagem do indicador THP
            if env.now > fora_transitorio and thp_inicio != -1:
                thp = env.now - thp_inicio
            
                #Armazenamento do THP
                if thp > 0:
                    valores[id_trem-1].thp.append(thp)
                
            #Atualizacao de setor
            sb_ant = sb
            
            #Retorno da unidade de controle sobre proximo tipo de SB
            r = aguarda_CCO.value
            sb = r[0]
    
    
            printf("   Trem #%s liberado pelo CCO para seguir até setor #%s na sb #%s" % (id_trem, prox_setor, sb) )
            
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
                    valores[id_trem-1].setor.append(setor)
                    valores[id_trem-1].instante.append(env.now)
                
                #Tempo deslocamento na singela até liberar setor
                yield env.timeout(timeOut('deslocamento')) #timeout(5)
                printf("   Trem #%s liberou setor anterior #%s em %s min" % (id_trem, setor, env.now)) 
            
                if(setor>=0 and setor < num_setores):
                    ferrovia_linha[setor]["LINHA"][sb_ant][FERR_RECURSO].release(\
                                                    ferrovia_linha[setor]["LINHA"][sb_ant][FERR_REQ])
                
                Trigger_CCO()
                
                yield env.timeout(timeOut('liberar_cauda')) #timeout(1)
                        
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
                        valores[id_trem-1].setor.append(setor)
                        valores[id_trem-1].instante.append(env.now)
                    
                    yield env.timeout(timeOut('deslocamento')) #timeout(5)
    
                    if env.now > fora_transitorio:
                        valores[id_trem-1].setor.append(setor+1)
                        valores[id_trem-1].instante.append(env.now)
                    yield env.timeout(timeOut('deslocamento')) #timeout(5)
    
                    if env.now > fora_transitorio:                
                        valores[id_trem-1].setor.append(setor+1)
                        valores[id_trem-1].instante.append(env.now)
                        
                    printf("   Trem #%s chegou no destino subindo (mina) " % (id_trem)) 
                    ferrovia_linha[setor]["LINHA"][sb][FERR_RECURSO].release(\
                                ferrovia_linha[setor]["LINHA"][sb][FERR_REQ])
                    out = 1
                    dir = -1
    
                elif setor == 0 and dir == -1:
                    #Chegada a unidade demandante            
                    print("Trem %d chegou a unidade demandante %d" % (id_trem,env.now))                
                    
                    if env.now > fora_transitorio:                            
                        valores[id_trem-1].setor.append(0)
                        valores[id_trem-1].instante.append(env.now)
                    yield env.timeout(timeOut('deslocamento')) 
    
                    if env.now > fora_transitorio:
                        valores[id_trem-1].setor.append(-1)
                        valores[id_trem-1].instante.append(env.now)
    
                    yield env.timeout(timeOut('deslocamento')) 
                    
                    if env.now > fora_transitorio:
                        valores[id_trem-1].setor.append(-1)
                        valores[id_trem-1].instante.append(env.now)
                    
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
              
    
    #Configurador da ferrovia
    def config_rail(env):
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
    
    
    env = simpy.Environment()
    config_rail(env)
    env.process(CCO(env))
  
    #Indisponibiliza setores
    for setor_ind in indisponiveis:
        nu_setor = int(setor_ind[0])
        
        if setor_ind[1] == 'A':
            tp_setor = 0
        else:
            tp_setor = 1
               
        ferrovia_linha[nu_setor]["LINHA"][tp_setor][FERR_RECURSO].request()
  
    
   
    env.process(trem(env=env,out=1,setor=0,dir=1,sb=-1))
    env.process(trem(env=env,out=1,setor=0,dir=1,sb=-1))
    env.process(trem(env=env,out=1,setor=0,dir=1,sb=-1))
    
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
    
    gerar_estatisticas()
    
    st.plotly_chart(fim_simulation(), use_container_width=True)
        
    