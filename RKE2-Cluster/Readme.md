## Bu Ansible RKE2'nin 1.31 versiyonları ile birlikte EKS Distro kurulumunu sağlamak amacıyla yazılmıştır.
## Kurulum başlangıç olarak Yum paket yöneticisini destekleyecek şekilde hazırlanmıştır, Centos ve Oracle Linux sunucularında kurulumları sağlıklı şekilde tamamlamıştır.



## Kurulum Öncesi

#### 1 - inventory/cluster/hosts.ini  dosyasını açın. Bunun dışında Node isimlerini IP adreslerini güncelleyebilirsiniz.
###### a. Hosts dosyası içerisinde bulunan rke2_type temelde 3 farklı key için tanımlanmıştır. Bu keyler server, active, agent olarak geçmektedir. server ve active doğrudan master nodeları temsil eder, agent ise workerlar için kullanılmalıdır.
###### b. Server tipinde sadece 1 tane master mutlaka olmalıdır.

#### 2 - inventory/cluster/group_vars/k8s_cluster.yaml dosyasını açın. Bu dosya sizin tüm nodelarınız ve kurulum süreciniz için ayarlanması gereken variableları içermektedir.
###### a. rke2_data_dir değişkeni RKE2'nin tüm datasını farklı bir dizinde tutmak isterseniz kullanabileceğiniz değişkendir. Default: /var/lib/rancher/rke2
###### c. rke2_ha_mode_keepalived değişkeni keepalived'nin kurulum süreci için eklenmiştir, şu anda aktif değildir.
###### d. rke2_api_ip değişkeni rke2_type'ı server belirlenmiş bir sunucunun IP adresini içermelidir.
###### e. rke2_additional_sans bu değişken master nodelar için gerekli sertifika ayarlamaları için kullanılır. Tüm master nodeların burada alt alta eklenmesi gerekmektedir.
###### f. rke2_token bu değişken RKE2'de nodeların register olma sürecinde attıkları isteklerde kullanılır, kurulum öncesinde karmaşık harf ve sayı içeren bir key oluşturularak güncellenebilir.
###### g. rke2_version bu değişken kurulum sürecinde, RKE2'nin hangi versiyonu kurulacağını yönetmek için kullanılır, burada geçilen değişkene bağlı olarak EKS Distro imageları otomatik olarak ayarlanır. (Desteklenen versiyonlar [v1.19.14+rke2r1, v1.20.11+rke2r2, v1.21.10+rke2r1])
###### h. custom_registry bu değişken authentication gereken bir registry kullanılacaksa gerekmektedir. active ya da deactive olarak parametresi değiştirilebilir.
###### __ h1. registry_address değişkeni doğrudan registry'nizin adresi olmalıdır. Örn: private.registry.com
###### __ h2. registry_user registry'inize login için gerekli username
###### __ h3. registry_password registry'inize login için gerekli password
###### __ i. custom_mirror değişkeni mirrorlanmak istenen bir registry var olduğunda kullanılır, aynı zamanda insecure durumda https kullanılan bir registry'e erişim için de kullanılması gerekir. Değişkenleri active ve deactive şeklindedir. 
###### __ i1. custom_registry ile custom_mirror aynı anda kullanılması gerekmemektedir. custom_mirror custom_registry'i kapsamaktadır.
###### __ i2. registry_address değişkeni doğrudan registry'nizin adresi olmalıdır. Örn: private.registry.com
###### __ i3. registry_mirror değişkeni mirrorlanmasını istediğiniz registry'nizin adresi olmalıdır. Örn: private.registry.com
###### __ i4. registry_user registry'inize login için gerekli username
###### __ i5. registry_password registry'inize login için gerekli password


## Kurulum'a başlarken

#### 1 - Cluster kurulumuna başlamak için, [ ansible-playbook -i inventory/cluster/hosts.ini cluster_install.yaml ] komutu basılmalı. Kurulum sunucusu sayısına bağlı olarak değişkenlik gösterebilir. Ortama 10-15 dakikalık bir süre gerekecektir.

## Kurulum tamamlandıktan sonra cluster'da bulunan kubeconfig, bulunduğunuz ansible dizini altına rke2.yaml adıyla çekilecektir.

## Not: Kurulum sonrasında private registry ekleyebilirsiniz. Bunun için gereken, [ ansible-playbook -i inventory/cluster/hosts.ini registries.yaml ] komutunu çalıştırmak. DIKKAT: Bu işlem sırasında worker nodelarda reboot atılacaktır

## Kurulumu tamamen ya da belirli nodelardan silmek için

#### 1 - [ ansible-playbook -i inventory/cluster/hosts.ini uninstall_cluster.yaml ] komutunu çalıştırmak yeterli olacaktır. 

## Silme işlemi öncesi hosts.ini dosyasından silinmesini istemediğiniz nodeları kaldırmayı unutmayın.

## Yeni Worker node eklemek için

#### 1 - hosts.ini dosyası içerisinde 'workers' kısmına sadece yeni nodeları ekleyin, eski nodeları yorum satırına alın.
#### 2 - [ ansible-playbook -i inventory/cluster/hosts.ini node_adding.yaml ] komutunu çalıştırmak yeterli olacaktır.
