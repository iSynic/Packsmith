#include <QApplication>
#include <QAbstractTableModel>
#include <QElapsedTimer>
#include <QFile>
#include <QFontDatabase>
#include <QJsonDocument>
#include <QJsonObject>
#include <QProcess>
#include <QTableView>
#include <QTimer>
#include <iostream>

class Entries: public QAbstractTableModel {
public:
    int rowCount(const QModelIndex &parent={}) const override {return parent.isValid()?0:100000;}
    int columnCount(const QModelIndex &parent={}) const override {return parent.isValid()?0:2;}
    QVariant data(const QModelIndex &index,int role=Qt::DisplayRole) const override {
        if(!index.isValid()||role!=Qt::DisplayRole) return {};
        return index.column()==0 ? QVariant(QString("entries/%1.txt").arg(index.row(),6,10,QChar('0'))) : QVariant(1);
    }
};

int main(int argc,char **argv) {
    QApplication app(argc,argv);
#ifdef Q_OS_WIN
    int fontId=QFontDatabase::addApplicationFont("C:/Windows/Fonts/segoeui.ttf");
    if(fontId>=0) app.setFont(QFont(QFontDatabase::applicationFontFamilies(fontId).first(),10));
#else
    int fontId=QFontDatabase::addApplicationFont("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf");
    if(fontId>=0) app.setFont(QFont(QFontDatabase::applicationFontFamilies(fontId).first(),10));
#endif
    if(argc!=4) return 2;
    Entries model;QTableView view;view.setModel(&model);view.resize(900,500);
    view.setWindowTitle("Archive assessment: 100,000 entries");view.show();
    QElapsedTimer timer;timer.start();qint64 previous=0,maxGap=0,cancelRequested=-1,finishedAt=-1;
    int ticks=0;bool childStarted=false;QProcess child;QTimer heartbeat;
    QObject::connect(&heartbeat,&QTimer::timeout,[&]{auto now=timer.elapsed();maxGap=qMax(maxGap,now-previous);previous=now;++ticks;});
    heartbeat.start(10);
    QObject::connect(&child,&QProcess::started,[&]{childStarted=true;});
    QObject::connect(&child,&QProcess::readyReadStandardOutput,[&]{child.readAllStandardOutput();});
    QObject::connect(&child,&QProcess::readyReadStandardError,[&]{child.readAllStandardError();});
    QObject::connect(&child,qOverload<int,QProcess::ExitStatus>(&QProcess::finished),[&](int,QProcess::ExitStatus){finishedAt=timer.elapsed();});
    child.setProgram(argv[1]);child.setArguments({"l","-slt",argv[2]});child.start();
    QTimer::singleShot(75,[&]{if(child.state()!=QProcess::NotRunning){cancelRequested=timer.elapsed();child.kill();}});
    QTimer::singleShot(500,[&]{
        view.selectRow(99999);view.scrollTo(model.index(99999,0));
        view.grab().save(QString(argv[3])+".png");
        QJsonObject result{{"font_loaded",fontId>=0},{"qt_version",qVersion()},{"platform_plugin",QApplication::platformName()},{"model_rows",model.rowCount()},{"heartbeat_ticks",ticks},{"maximum_event_gap_ms",maxGap},{"worker_started",childStarted},{"cancel_requested_ms",cancelRequested},{"worker_finished_ms",finishedAt},{"cancel_latency_ms",cancelRequested>=0&&finishedAt>=cancelRequested?finishedAt-cancelRequested:-1},{"evidence_limit","Synthetic table model and process listing probe; not a production archive UI or accessibility test"}};
        QFile file(QString(argv[3])+".json");file.open(QIODevice::WriteOnly);file.write(QJsonDocument(result).toJson());
        std::cout<<QJsonDocument(result).toJson(QJsonDocument::Compact).constData()<<std::endl;
        app.exit(childStarted&&ticks>5?0:1);
    });
    QTimer::singleShot(10000,[&]{child.kill();app.exit(3);});
    return app.exec();
}
